import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { notify } from '../utils/notificaciones';

const AlertasCriticas = () => {
    const [productosStockBajo, setProductosStockBajo] = useState([]);
    const [loadingStock, setLoadingStock] = useState(false);
    const [loadingEscaneo, setLoadingEscaneo] = useState(false);
    const [ultimoEscaneo, setUltimoEscaneo] = useState(null);

    const cargarProductosStockBajo = async () => {
        try {
            setLoadingStock(true);
            const token = localStorage.getItem('access_token');
            const config = { headers: { 'Authorization': `Bearer ${token}` } };
            
            const res = await axios.get('http://127.0.0.1:8000/api/gestion/productos/stock_bajo/', config);
            setProductosStockBajo(res.data.productos || []);
        } catch (err) {
            console.error('Error al cargar productos con stock bajo:', err);
            notify.error('No pudimos cargar el inventario');
        } finally {
            setLoadingStock(false);
        }
    };

    useEffect(() => {
        cargarProductosStockBajo();
    }, []);

    const escanearHuecos = async () => {
        try {
            setLoadingEscaneo(true);
            const token = localStorage.getItem('access_token');
            const config = { headers: { 'Authorization': `Bearer ${token}` } };
            
            const res = await axios.post('http://127.0.0.1:8000/api/gestion/promociones/escanear-huecos/', {}, config);
            
            setUltimoEscaneo(new Date());
            notify.success(`✅ Escaneo completado: ${res.data.promos_creadas || 0} promociones generadas`);
        } catch (err) {
            console.error('Error al escanear huecos:', err);
            const msgError = err.response?.data?.error || 'Error al escanear agenda';
            notify.error(msgError);
        } finally {
            setLoadingEscaneo(false);
        }
    };

    return (
        <div className="space-y-6">
            {/* SECCIÓN 1: ALERTAS DE STOCK BAJO */}
            <div className="bg-white rounded-xl shadow-lg overflow-hidden border-l-4 border-red-500">
                <div className="bg-gradient-to-r from-red-50 to-red-100 p-4 border-b-2 border-red-200">
                    <h2 className="text-lg font-bold text-red-800 flex items-center gap-2">
                        <span className="text-2xl">⚠️</span> Productos con Stock Bajo
                    </h2>
                    <p className="text-sm text-red-700 mt-1">
                        {productosStockBajo.length} producto(s) necesitan reabastecimiento
                    </p>
                </div>

                <div className="p-4">
                    {loadingStock ? (
                        <div className="flex justify-center items-center py-8">
                            <div className="animate-spin h-8 w-8 text-red-500 border-4 border-red-200 border-t-red-500 rounded-full"></div>
                        </div>
                    ) : productosStockBajo.length === 0 ? (
                        <div className="text-center py-8 text-gray-500">
                            <p className="text-lg font-semibold mb-2">✅ Todo el inventario está en orden</p>
                            <p className="text-sm">No hay productos con stock bajo</p>
                        </div>
                    ) : (
                        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                            {productosStockBajo.map(producto => (
                                <div
                                    key={producto.id}
                                    className="bg-gradient-to-br from-red-50 to-red-100 rounded-lg p-4 border-2 border-red-300 hover:shadow-md transition-all"
                                >
                                    <div className="flex items-start justify-between mb-2">
                                        <h3 className="font-bold text-red-900 text-sm flex-1">
                                            {producto.nombre}
                                        </h3>
                                        <span className="ml-2 text-red-600 font-bold text-lg">!</span>
                                    </div>

                                    <div className="space-y-2 text-sm">
                                        <div className="flex justify-between">
                                            <span className="text-gray-700">Stock actual:</span>
                                            <span className="font-bold text-red-600">{producto.stock} unid.</span>
                                        </div>
                                        <div className="flex justify-between">
                                            <span className="text-gray-700">Stock mínimo:</span>
                                            <span className="font-bold text-orange-600">{producto.stock_minimo} unid.</span>
                                        </div>

                                        {/* Barra de progreso */}
                                        <div className="mt-3">
                                            <div className="w-full bg-red-200 rounded-full h-2">
                                                <div
                                                    className="bg-red-600 h-2 rounded-full"
                                                    style={{
                                                        width: `${Math.min((producto.stock / producto.stock_minimo) * 100, 100)}%`
                                                    }}
                                                ></div>
                                            </div>
                                        </div>

                                        {/* Déficit */}
                                        <div className="bg-red-200 rounded px-2 py-1 text-center">
                                            <span className="text-red-800 font-semibold text-xs">
                                                Falta: {Math.max(0, producto.stock_minimo - producto.stock)} unid.
                                            </span>
                                        </div>
                                    </div>

                                    {/* Botón de reabastecimiento */}
                                    <button className="w-full mt-3 bg-red-500 hover:bg-red-600 text-white font-bold py-2 rounded transition-all text-sm">
                                        📦 Reabastecer
                                    </button>
                                </div>
                            ))}
                        </div>
                    )}
                </div>
            </div>

            {/* SECCIÓN 2: ESCANEO DE HUECOS */}
            <div className="bg-white rounded-xl shadow-lg overflow-hidden border-l-4 border-blue-500">
                <div className="bg-gradient-to-r from-blue-50 to-blue-100 p-4 border-b-2 border-blue-200">
                    <h2 className="text-lg font-bold text-blue-800 flex items-center gap-2">
                        <span className="text-2xl">📅</span> Genera Promociones Last Minute
                    </h2>
                    <p className="text-sm text-blue-700 mt-1">
                        Detecta automáticamente huecos en la agenda y crea ofertas flash
                    </p>
                </div>

                <div className="p-6">
                    <div className="bg-blue-50 rounded-lg p-4 mb-6">
                        <p className="text-gray-700 text-sm mb-3">
                            🔍 Este sistema automáticamente:
                        </p>
                        <ul className="text-sm text-gray-600 space-y-1 ml-4">
                            <li>✓ Escanea los próximos 3 días de agenda</li>
                            <li>✓ Identifica huecos mayores a 3 horas</li>
                            <li>✓ Crea promociones flash con descuento</li>
                            <li>✓ Notifica a clientes con disponibilidad</li>
                        </ul>
                    </div>

                    <div className="space-y-3">
                        {ultimoEscaneo && (
                            <div className="bg-green-50 border border-green-300 rounded-lg p-3 text-sm">
                                <p className="text-green-800 font-semibold">
                                    ✅ Último escaneo realizado
                                </p>
                                <p className="text-green-700 text-xs mt-1">
                                    {ultimoEscaneo.toLocaleString('es-AR')}
                                </p>
                            </div>
                        )}

                        <button
                            onClick={escanearHuecos}
                            disabled={loadingEscaneo}
                            className={`
                                w-full py-3 px-4 rounded-lg font-bold text-white
                                transition-all transform hover:scale-105 active:scale-95
                                flex items-center justify-center gap-2
                                ${loadingEscaneo
                                    ? 'bg-blue-300 cursor-not-allowed opacity-75'
                                    : 'bg-gradient-to-r from-blue-500 to-blue-600 hover:shadow-lg'
                                }
                            `}
                        >
                            {loadingEscaneo ? (
                                <>
                                    <div className="animate-spin h-5 w-5 border-2 border-white border-t-transparent rounded-full"></div>
                                    Escaneando...
                                </>
                            ) : (
                                <>
                                    <span>🚀</span> Escanear Huecos Ahora
                                </>
                            )}
                        </button>
                    </div>
                </div>
            </div>
        </div>
    );
};

export default AlertasCriticas;
