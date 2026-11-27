import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { useNavigate, useLocation, useParams } from 'react-router-dom';
import { notify } from '../../utils/notificaciones';
import { IconBag, IconClock, IconGift, IconInfo, IconSparkles } from '../../components/common/Icons';

const DetallePromocion = () => {
    const navigate = useNavigate();
    const location = useLocation();
    const { id } = useParams();
    
    const [promocion, setPromocion] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState('');
    const [tiempoRestante, setTiempoRestante] = useState(null);

    // Obtener promoción desde state o desde params
    const promoId = location.state?.promoId || id;

    useEffect(() => {
        const cargarPromocion = async () => {
            try {
                setLoading(true);
                const res = await axios.get(
                    `http://127.0.0.1:8000/api/gestion/promociones/${promoId}/`
                );
                setPromocion(res.data);
            } catch (err) {
                console.error('Error cargando promoción:', err);
                setError('No pudimos cargar la promoción. Intenta luego.');
                notify.error('Promoción no encontrada');
            } finally {
                setLoading(false);
            }
        };

        if (promoId) {
            cargarPromocion();
        }
    }, [promoId]);

    // Calcular tiempo restante si es LAST_MINUTE
    useEffect(() => {
        if (!promocion || promocion.tipo !== 'LAST_MINUTE') return;

        const calcularTiempoRestante = () => {
            const ahora = new Date();
            const vencimiento = new Date(promocion.fecha_vencimiento);
            const diferencia = vencimiento - ahora;

            if (diferencia <= 0) {
                setTiempoRestante('Expirada');
                return;
            }

            const horas = Math.floor(diferencia / (1000 * 60 * 60));
            const minutos = Math.floor((diferencia % (1000 * 60 * 60)) / (1000 * 60));
            const segundos = Math.floor((diferencia % (1000 * 60)) / 1000);

            setTiempoRestante(`${horas}h ${minutos}m ${segundos}s`);
        };

        calcularTiempoRestante();
        const interval = setInterval(calcularTiempoRestante, 1000);
        return () => clearInterval(interval);
    }, [promocion]);

    if (loading) {
        return (
            <div className="min-h-screen bg-gradient-to-b from-pink-50 to-white flex items-center justify-center">
                <div className="text-center">
                    <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-pink-600 mx-auto mb-4"></div>
                    <p className="text-gray-600">Cargando promoción...</p>
                </div>
            </div>
        );
    }

    if (error || !promocion) {
        return (
            <div className="min-h-screen bg-gradient-to-b from-pink-50 to-white flex items-center justify-center">
                <div className="text-center">
                    <p className="text-red-600 mb-4">{error}</p>
                    <button
                        onClick={() => navigate('/catalogo-productos')}
                        className="px-4 py-2 bg-pink-600 text-white rounded-lg hover:bg-pink-700 transition"
                    >
                        Volver al catálogo
                    </button>
                </div>
            </div>
        );
    }

    return (
        <div className="min-h-screen bg-gradient-to-b from-pink-50 to-white p-4 sm:p-6">
            {/* Header */}
            <div className="max-w-2xl mx-auto mb-6">
                <button
                    onClick={() => navigate(-1)}
                    className="flex items-center text-pink-600 hover:text-pink-700 transition mb-4"
                >
                    <span className="mr-2">←</span>
                    <span>Volver</span>
                </button>
            </div>

            {/* Card Principal */}
            <div className="max-w-2xl mx-auto bg-white rounded-xl shadow-lg overflow-hidden">
                {/* Badge de tipo */}
                <div className="bg-gradient-to-r from-pink-600 to-rose-500 text-white p-4 sm:p-6">
                    <div className="flex items-center justify-between mb-2">
                        <h1 className="text-2xl sm:text-3xl font-bold">{promocion.nombre}</h1>
                        <span className={`px-4 py-2 rounded-full text-sm font-bold whitespace-nowrap ${
                            promocion.tipo === 'LAST_MINUTE' 
                                ? 'bg-red-500 text-white' 
                                : promocion.tipo === 'RETOQUE'
                                ? 'bg-purple-500 text-white'
                                : 'bg-blue-500 text-white'
                        }`}>
                            {promocion.tipo === 'LAST_MINUTE' && (
                                <span className="inline-flex items-center gap-2">
                                    <IconClock className="h-4 w-4" /> ULTIMA HORA
                                </span>
                            )}
                            {promocion.tipo === 'RETOQUE' && (
                                <span className="inline-flex items-center gap-2">
                                    <IconSparkles className="h-4 w-4" /> RETOQUE
                                </span>
                            )}
                            {promocion.tipo === 'COMBO' && (
                                <span className="inline-flex items-center gap-2">
                                    <IconGift className="h-4 w-4" /> COMBO
                                </span>
                            )}
                        </span>
                    </div>
                    
                    {/* Descripción */}
                    <p className="text-pink-50 text-sm sm:text-base">{promocion.descripcion}</p>

                    {/* Contador para LAST_MINUTE */}
                    {promocion.tipo === 'LAST_MINUTE' && tiempoRestante && tiempoRestante !== 'Expirada' && (
                        <div className="mt-4 bg-red-900 bg-opacity-50 p-3 rounded-lg">
                            <p className="text-sm font-bold inline-flex items-center gap-2">
                                <IconClock className="h-4 w-4" /> Válido por:
                            </p>
                            <p className="text-xl font-bold text-yellow-300">{tiempoRestante}</p>
                        </div>
                    )}
                </div>

                {/* Contenido */}
                <div className="p-4 sm:p-6 space-y-6">
                    {/* Descuento */}
                    {promocion.descuento && (
                        <div className="bg-gradient-to-r from-green-50 to-emerald-50 border-2 border-green-300 p-4 rounded-lg">
                            <p className="text-sm text-gray-600 mb-1">Descuento</p>
                            <p className="text-3xl font-bold text-green-600">{promocion.descuento}%</p>
                        </div>
                    )}

                    {/* Servicios incluidos */}
                    {promocion.servicios && promocion.servicios.length > 0 && (
                        <div>
                            <h3 className="text-lg font-bold text-gray-900 mb-3 flex items-center">
                                <IconSparkles className="h-5 w-5 mr-2" />
                                Servicios incluidos ({promocion.servicios.length})
                            </h3>
                            <div className="space-y-2">
                                {promocion.servicios.map((servicio) => (
                                    <div key={servicio.id} className="bg-gray-50 p-3 rounded-lg border border-gray-200">
                                        <p className="font-semibold text-gray-900">{servicio.nombre}</p>
                                        {servicio.duracion_estimada && (
                                                <p className="text-sm text-gray-600 inline-flex items-center gap-2">
                                                    <IconClock className="h-4 w-4" /> {servicio.duracion_estimada} min
                                                </p>
                                        )}
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}

                    {/* Productos incluidos */}
                    {promocion.productos && promocion.productos.length > 0 && (
                        <div>
                            <h3 className="text-lg font-bold text-gray-900 mb-3 flex items-center">
                                <IconBag className="h-5 w-5 mr-2" />
                                Productos incluidos ({promocion.productos.length})
                            </h3>
                            <div className="space-y-2">
                                {promocion.productos.map((producto) => (
                                    <div key={producto.id} className="bg-gray-50 p-3 rounded-lg border border-gray-200">
                                        <p className="font-semibold text-gray-900">{producto.nombre}</p>
                                        {producto.precio && (
                                            <p className="text-sm text-gray-600">
                                                ${producto.precio}
                                            </p>
                                        )}
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}

                    {/* Condiciones */}
                    {promocion.condiciones && (
                        <div className="bg-blue-50 border-2 border-blue-200 p-4 rounded-lg">
                            <p className="text-sm text-gray-700">
                                <span className="font-bold text-blue-900 inline-flex items-center gap-2">
                                    <IconInfo className="h-4 w-4" /> Condiciones:
                                </span> {promocion.condiciones}
                            </p>
                        </div>
                    )}

                    {/* Fecha de validez */}
                    <div className="bg-gray-50 p-4 rounded-lg border border-gray-200">
                        <p className="text-sm text-gray-600 mb-1">Válida hasta</p>
                        <p className="font-bold text-gray-900">
                            {new Date(promocion.fecha_vencimiento).toLocaleDateString('es-AR', {
                                weekday: 'long',
                                year: 'numeric',
                                month: 'long',
                                day: 'numeric'
                            })}
                        </p>
                    </div>
                </div>

                {/* Footer con CTA */}
                <div className="bg-gradient-to-r from-pink-50 to-rose-50 p-4 sm:p-6 border-t border-gray-100">
                    <button
                        onClick={() => {
                            notify.success('¡Promoción guardada!');
                            navigate('/reserva', {
                                state: {
                                    promoId: promocion.id
                                }
                            });
                        }}
                        className="w-full bg-gradient-to-r from-pink-600 to-rose-500 text-white font-bold py-3 rounded-lg hover:from-pink-700 hover:to-rose-600 transition shadow-lg"
                    >
                            <span className="inline-flex items-center gap-2">
                                <IconSparkles className="h-4 w-4" /> Reservar con esta promoción
                            </span>
                    </button>
                </div>
            </div>
        </div>
    );
};

export default DetallePromocion;
