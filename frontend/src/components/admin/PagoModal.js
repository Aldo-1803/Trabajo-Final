import React, { useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { notify } from '../../utils/notificaciones';

const PagoModal = ({
    isOpen,
    onClose,
    origen,
    origenTipo,
    onPagoRegistrado,
    defaultMetodoPago,
    defaultEsSena,
    defaultMonto,
    lockMetodoPago = false,
    lockEsSena = false,
    lockMonto = false
}) => {
    const [monto, setMonto] = useState('');
    const [metodoPago, setMetodoPago] = useState('EFECTIVO');
    const [fechaPago, setFechaPago] = useState('');
    const [comprobante, setComprobante] = useState(null);
    const [esSena, setEsSena] = useState(false);
    const [procesando, setProcesando] = useState(false);

    const saldoPendiente = useMemo(() => {
        if (!origen || !origen.total) return null;
        const total = Number(origen.total || 0);
        const pagos = (origen.pagos || []).reduce((acc, pago) => acc + Number(pago.monto || 0), 0);
        return Math.max(0, total - pagos);
    }, [origen]);

    useEffect(() => {
        if (!isOpen) return;
        if (defaultMetodoPago) {
            setMetodoPago(defaultMetodoPago);
        } else {
            setMetodoPago('EFECTIVO');
        }
        setFechaPago('');
        setComprobante(null);
        if (typeof defaultEsSena === 'boolean') {
            setEsSena(defaultEsSena);
        } else {
            setEsSena(false);
        }

        if (defaultMonto !== undefined && defaultMonto !== null && defaultMonto !== '') {
            setMonto(String(defaultMonto));
        } else if (saldoPendiente !== null) {
            setMonto(saldoPendiente > 0 ? String(saldoPendiente.toFixed(2)) : '');
        } else {
            setMonto('');
        }
    }, [isOpen, saldoPendiente, defaultMetodoPago, defaultEsSena, defaultMonto]);

    if (!isOpen || !origen) return null;

    const handleSubmit = async (event) => {
        event.preventDefault();

        if (!monto || Number(monto) <= 0) {
            notify.error('Ingresa un monto valido.');
            return;
        }

        if (metodoPago === 'TRANSFERENCIA' && !comprobante) {
            notify.error('El comprobante es obligatorio para transferencias.');
            return;
        }

        const token = localStorage.getItem('access_token');
        const formData = new FormData();
        formData.append('monto', monto);
        formData.append('metodo_pago', metodoPago);
        if (fechaPago) {
            formData.append('fecha_pago', fechaPago);
        }
        formData.append('es_sena', esSena ? 'true' : 'false');
        if (comprobante) {
            formData.append('comprobante_foto', comprobante);
        }

        const endpoint = origenTipo === 'orden'
            ? `http://127.0.0.1:8000/api/gestion/ordenes-compra/${origen.id}/registrar_pago/`
            : `http://127.0.0.1:8000/api/gestion/turnos/${origen.id}/registrar_pago/`;

        setProcesando(true);
        try {
            const response = await axios.post(endpoint, formData, {
                headers: {
                    'Authorization': `Bearer ${token}`,
                    'Content-Type': 'multipart/form-data'
                }
            });
            notify.success('Pago registrado correctamente.');
            if (onPagoRegistrado) {
                onPagoRegistrado(response.data);
            }
            onClose();
        } catch (error) {
            console.error('Error registrando pago:', error.response?.data || error);
            const mensaje = error.response?.data?.comprobante_foto?.[0]
                || error.response?.data?.detail
                || 'Error al registrar el pago.';
            notify.error(mensaje);
        } finally {
            setProcesando(false);
        }
    };

    return (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
            <div className="bg-white rounded-lg shadow-xl w-full max-w-lg mx-4 p-6">
                <div className="flex items-start justify-between mb-4">
                    <div>
                        <h2 className="text-2xl font-bold text-gray-800">Registrar Pago</h2>
                        <p className="text-sm text-gray-500">
                            {origenTipo === 'orden' ? 'Orden de compra' : 'Turno'}
                        </p>
                    </div>
                    <button
                        onClick={onClose}
                        className="text-gray-500 hover:text-gray-700"
                        type="button"
                    >
                        ✕
                    </button>
                </div>

                <div className="mb-4 text-sm text-gray-700 bg-gray-50 rounded-md p-3">
                    <p><strong>Cliente:</strong> {origen.cliente_nombre || origen.cliente_email || '-'}</p>
                    {origen.codigo && <p><strong>Orden:</strong> {origen.codigo}</p>}
                    {origen.fecha && <p><strong>Fecha:</strong> {origen.fecha}</p>}
                    {origen.total && (
                        <p>
                            <strong>Total:</strong> ${Number(origen.total).toFixed(2)}
                        </p>
                    )}
                    {saldoPendiente !== null && (
                        <p><strong>Saldo pendiente:</strong> ${saldoPendiente.toFixed(2)}</p>
                    )}
                </div>

                <form onSubmit={handleSubmit}>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                        <div>
                            <label className="block text-sm font-medium text-gray-700 mb-1">Monto</label>
                            <input
                                type="number"
                                step="0.01"
                                value={monto}
                                onChange={(e) => setMonto(e.target.value)}
                                className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-rose-500"
                                placeholder="0.00"
                                required
                                disabled={lockMonto}
                            />
                        </div>
                        <div>
                            <label className="block text-sm font-medium text-gray-700 mb-1">Metodo de pago</label>
                            <select
                                value={metodoPago}
                                onChange={(e) => setMetodoPago(e.target.value)}
                                className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-rose-500"
                                disabled={lockMetodoPago}
                            >
                                <option value="EFECTIVO">Efectivo</option>
                                <option value="TRANSFERENCIA">Transferencia</option>
                            </select>
                        </div>
                        <div>
                            <label className="block text-sm font-medium text-gray-700 mb-1">Fecha de pago</label>
                            <input
                                type="datetime-local"
                                value={fechaPago}
                                onChange={(e) => setFechaPago(e.target.value)}
                                className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-rose-500"
                            />
                        </div>
                        <div>
                            <label className="block text-sm font-medium text-gray-700 mb-1">Comprobante</label>
                            <input
                                type="file"
                                accept="image/*,application/pdf"
                                onChange={(e) => setComprobante(e.target.files[0])}
                                className="w-full text-sm"
                            />
                        </div>
                    </div>

                    <div className="mt-4 flex items-center gap-2">
                        <input
                            id="es-sena"
                            type="checkbox"
                            checked={esSena}
                            onChange={(e) => setEsSena(e.target.checked)}
                            disabled={lockEsSena}
                        />
                        <label htmlFor="es-sena" className="text-sm text-gray-700">Es seña</label>
                    </div>

                    <div className="mt-6 flex justify-end gap-3">
                        <button
                            type="button"
                            onClick={onClose}
                            className="px-4 py-2 text-gray-700 bg-gray-200 rounded-md hover:bg-gray-300"
                            disabled={procesando}
                        >
                            Cancelar
                        </button>
                        <button
                            type="submit"
                            className="px-4 py-2 text-white bg-rose-600 rounded-md hover:bg-rose-700"
                            disabled={procesando}
                        >
                            {procesando ? 'Registrando...' : 'Registrar pago'}
                        </button>
                    </div>
                </form>
            </div>
        </div>
    );
};

export default PagoModal;
