import React, { useCallback, useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { notify } from '../../utils/notificaciones';

const HistorialPagos = () => {
    const [pagos, setPagos] = useState([]);
    const [loading, setLoading] = useState(true);
    const [filtroHoy, setFiltroHoy] = useState(false);
    const [filtroMetodo, setFiltroMetodo] = useState('TODOS');
    const [configuracion, setConfiguracion] = useState(null);

    const cargarPagos = useCallback(async () => {
        setLoading(true);
        try {
            const token = localStorage.getItem('access_token');
            const params = new URLSearchParams();

            if (filtroHoy) {
                params.append('solo_hoy', '1');
            }
            if (filtroMetodo !== 'TODOS') {
                params.append('metodo_pago', filtroMetodo);
            }

            const url = `http://127.0.0.1:8000/api/gestion/pagos/?${params.toString()}`;
            const res = await axios.get(url, {
                headers: { 'Authorization': `Bearer ${token}` }
            });

            setPagos(res.data.results || res.data);
        } catch (error) {
            console.error('Error cargando pagos:', error);
            notify.error('Error al cargar el historial de pagos');
        } finally {
            setLoading(false);
        }
    }, [filtroHoy, filtroMetodo]);

    useEffect(() => {
        cargarPagos();
    }, [cargarPagos]);

    useEffect(() => {
        const cargarConfiguracion = async () => {
            try {
                const token = localStorage.getItem('access_token');
                const res = await axios.get('/api/gestion/configuracion/', {
                    headers: token ? { 'Authorization': `Bearer ${token}` } : {}
                });
                let configData = null;

                if (res.data?.results?.length) {
                    configData = res.data.results[0];
                } else if (Array.isArray(res.data) && res.data.length > 0) {
                    configData = res.data[0];
                } else if (res.data && typeof res.data === 'object' && res.data.id) {
                    configData = res.data;
                }

                setConfiguracion(configData || null);
            } catch (error) {
                console.error('Error cargando configuracion:', error);
            }
        };

        cargarConfiguracion();
    }, []);

    const totalCaja = useMemo(() => {
        return pagos.reduce((acc, pago) => acc + Number(pago.monto || 0), 0);
    }, [pagos]);

    const imprimirComprobante = (pago) => {
        const fecha = pago.fecha_pago ? new Date(pago.fecha_pago).toLocaleString('es-AR') : '-';
        const metodo = pago.metodo_pago === 'TRANSFERENCIA' ? 'Transferencia' : 'Efectivo';
        const origen = pago.tipo_origen === 'ORDEN'
            ? `Orden ${pago.orden_codigo || ''}`
            : `Turno ${pago.turno_fecha || ''}`;
        const cliente = pago.cliente_nombre || pago.cliente_email || '-';
        const nombreEmpresa = configuracion?.empresa_nombre || 'Bohemia Hair';
        const razonSocial = configuracion?.comprobante_razon_social || nombreEmpresa;
        const cuil = configuracion?.comprobante_cuil || '-';
        const fechaInicioActividad = configuracion?.comprobante_fecha_inicio_actividad
            ? new Date(configuracion.comprobante_fecha_inicio_actividad).toLocaleDateString('es-AR')
            : '-';

        const contenido = `
            <html>
                <head>
                    <title>Comprobante de Pago</title>
                    <style>
                        body { font-family: Arial, sans-serif; padding: 24px; }
                        h1 { margin-bottom: 4px; }
                        .muted { color: #555; }
                        .box { border: 1px solid #ddd; padding: 16px; margin-top: 16px; }
                    </style>
                </head>
                <body>
                    <h1>Comprobante de Pago</h1>
                    <p class="muted">${nombreEmpresa}</p>
                    <p class="muted">${razonSocial}</p>
                    <p class="muted">CUIL: ${cuil}</p>
                    <p class="muted">Inicio de actividad: ${fechaInicioActividad}</p>
                    <div class="box">
                        <p><strong>Fecha:</strong> ${fecha}</p>
                        <p><strong>Cliente:</strong> ${cliente}</p>
                        <p><strong>Origen:</strong> ${origen}</p>
                        <p><strong>Monto:</strong> $${Number(pago.monto || 0).toFixed(2)}</p>
                        <p><strong>Metodo:</strong> ${metodo}</p>
                        <p><strong>Seña:</strong> ${pago.es_sena ? 'Si' : 'No'}</p>
                    </div>
                </body>
            </html>
        `;

        const ventana = window.open('', '_blank', 'width=600,height=700');
        if (!ventana) {
            notify.error('No se pudo abrir la ventana de impresion.');
            return;
        }
        ventana.document.write(contenido);
        ventana.document.close();
        ventana.focus();
        ventana.print();
    };

    if (loading) {
        return <div className="p-6 text-center">Cargando pagos...</div>;
    }

    return (
        <div className="p-6 bg-white rounded-lg">
            <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4 mb-6">
                <div>
                    <h1 className="text-3xl font-bold">Historial de Pagos / Caja</h1>
                    <p className="text-sm text-gray-500">Resumen de ingresos registrados</p>
                </div>
                <div className="bg-emerald-50 text-emerald-700 px-4 py-2 rounded-lg font-semibold">
                    Total caja: ${totalCaja.toFixed(2)}
                </div>
            </div>

            <div className="flex flex-wrap gap-3 mb-6">
                <button
                    onClick={() => setFiltroHoy((prev) => !prev)}
                    className={`px-4 py-2 rounded-full text-sm font-semibold ${
                        filtroHoy ? 'bg-emerald-600 text-white' : 'bg-gray-200 text-gray-700'
                    }`}
                >
                    {filtroHoy ? 'Pagos de hoy' : 'Ver pagos de hoy'}
                </button>
                {['TODOS', 'TRANSFERENCIA', 'EFECTIVO'].map((metodo) => (
                    <button
                        key={metodo}
                        onClick={() => setFiltroMetodo(metodo)}
                        className={`px-4 py-2 rounded-full text-sm font-semibold ${
                            filtroMetodo === metodo ? 'bg-slate-800 text-white' : 'bg-gray-200 text-gray-700'
                        }`}
                    >
                        {metodo === 'TODOS' ? 'Todos' : metodo}
                    </button>
                ))}
            </div>

            <div className="overflow-x-auto">
                <table className="w-full border-collapse">
                    <thead>
                        <tr style={{ backgroundColor: '#E8DCC4' }}>
                            <th className="p-3 text-left">Fecha</th>
                            <th className="p-3 text-left">Cliente</th>
                            <th className="p-3 text-left">Origen</th>
                            <th className="p-3 text-right">Monto</th>
                            <th className="p-3 text-center">Metodo</th>
                            <th className="p-3 text-center">Comprobante</th>
                            <th className="p-3 text-center">Acciones</th>
                        </tr>
                    </thead>
                    <tbody>
                        {pagos.length === 0 ? (
                            <tr>
                                <td colSpan="7" className="p-4 text-center text-gray-500">
                                    No hay pagos con estos filtros
                                </td>
                            </tr>
                        ) : (
                            pagos.map((pago) => (
                                <tr key={pago.id} className="border-b hover:bg-gray-50">
                                    <td className="p-3 text-sm">
                                        {pago.fecha_pago ? new Date(pago.fecha_pago).toLocaleString('es-AR') : '-'}
                                    </td>
                                    <td className="p-3 text-sm">
                                        <div className="font-semibold">{pago.cliente_nombre || '-'}</div>
                                        <div className="text-xs text-gray-500">{pago.cliente_email || ''}</div>
                                    </td>
                                    <td className="p-3 text-sm">
                                        {pago.tipo_origen === 'ORDEN'
                                            ? `Orden ${pago.orden_codigo || ''}`
                                            : `Turno ${pago.turno_fecha || ''}`}
                                    </td>
                                    <td className="p-3 text-right font-semibold">
                                        ${Number(pago.monto || 0).toFixed(2)}
                                    </td>
                                    <td className="p-3 text-center">
                                        <span className={`px-3 py-1 rounded-full text-xs font-semibold ${
                                            pago.metodo_pago === 'TRANSFERENCIA'
                                                ? 'bg-blue-100 text-blue-700'
                                                : 'bg-emerald-100 text-emerald-700'
                                        }`}>
                                            {pago.metodo_pago}
                                        </span>
                                    </td>
                                    <td className="p-3 text-center">
                                        {pago.comprobante_foto ? (
                                            <a
                                                href={pago.comprobante_foto}
                                                target="_blank"
                                                rel="noopener noreferrer"
                                                className="text-blue-600 hover:underline text-sm"
                                            >
                                                Ver
                                            </a>
                                        ) : (
                                            <span className="text-gray-400 text-sm">-</span>
                                        )}
                                    </td>
                                    <td className="p-3 text-center">
                                        <button
                                            onClick={() => imprimirComprobante(pago)}
                                            className="px-3 py-1 text-xs font-semibold rounded bg-gray-800 text-white hover:bg-gray-900"
                                        >
                                            Re-imprimir
                                        </button>
                                    </td>
                                </tr>
                            ))
                        )}
                    </tbody>
                </table>
            </div>
        </div>
    );
};

export default HistorialPagos;
