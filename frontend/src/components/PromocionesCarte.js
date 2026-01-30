import React, { useState, useEffect, useCallback } from 'react';
import axios from 'axios';

const PromocionesCarte = () => {
    const [promociones, setPromociones] = useState([]);
    const [loading, setLoading] = useState(true);
    const [tiemposRestantes, setTiemposRestantes] = useState({});

    const cargarPromociones = useCallback(async () => {
        try {
            setLoading(true);
            const res = await axios.get('http://127.0.0.1:8000/api/gestion/promociones/');
            // Filtrar por tipo: solo LAST_MINUTE y RETOQUE para el widget
            const filtradas = res.data.filter(p => 
                p.tipo === 'LAST_MINUTE' || p.tipo === 'RETOQUE'
            );
            setPromociones(filtradas);
        } catch (err) {
            console.error('Error al cargar promociones:', err);
            // No notificar error - es opcional si no hay conexión
        } finally {
            setLoading(false);
        }
    }, []);

    const actualizarTiemposRestantes = useCallback(() => {
        const nuevosTiempos = {};
        const ahora = new Date();

        promociones.forEach(promo => {
            if (promo.tipo === 'LAST_MINUTE') {
                // Si tiene fecha_especifica, usa esa fecha
                const fechaPromo = promo.fecha_especifica 
                    ? new Date(promo.fecha_especifica)
                    : new Date(promo.fecha_fin);
                
                // Si tiene hora_fin_promo, úsala
                if (promo.hora_fin_promo) {
                    const [horas, minutos, segundos] = promo.hora_fin_promo.split(':');
                    fechaPromo.setHours(parseInt(horas), parseInt(minutos), parseInt(segundos));
                } else {
                    fechaPromo.setHours(23, 59, 59);
                }

                const diferencia = fechaPromo - ahora;
                
                if (diferencia > 0) {
                    const horas = Math.floor(diferencia / (1000 * 60 * 60));
                    const minutos = Math.floor((diferencia % (1000 * 60 * 60)) / (1000 * 60));
                    const segundos = Math.floor((diferencia % (1000 * 60)) / 1000);
                    
                    nuevosTiempos[promo.id] = {
                        horas,
                        minutos,
                        segundos,
                        vigente: true
                    };
                } else {
                    nuevosTiempos[promo.id] = { vigente: false };
                }
            }
        });

        setTiemposRestantes(nuevosTiempos);
    }, [promociones]);

    useEffect(() => {
        cargarPromociones();
    }, [cargarPromociones]);

    // Actualizar contadores de tiempo cada segundo
    useEffect(() => {
        actualizarTiemposRestantes();
        const interval = setInterval(() => {
            actualizarTiemposRestantes();
        }, 1000);
        return () => clearInterval(interval);
    }, [actualizarTiemposRestantes]);

    if (loading) {
        return (
            <div className="p-4 bg-gradient-to-r from-rose-50 to-amber-50 rounded-lg animate-pulse">
                <div className="h-32 bg-gray-200 rounded"></div>
            </div>
        );
    }

    // Filtrar promociones vigentes (las expiradas no mostrar)
    const promocionesVigentes = promociones.filter(p => {
        if (p.tipo === 'LAST_MINUTE') {
            return tiemposRestantes[p.id]?.vigente !== false;
        }
        return true;
    });

    if (promocionesVigentes.length === 0) {
        return null; // No mostrar nada si no hay promociones
    }

    return (
        <div className="mb-8 animate-fade-in">
            <h2 className="text-xl font-bold text-gray-800 mb-4 flex items-center gap-2">
                <span className="text-2xl">✨</span> Promociones Exclusivas
            </h2>
            
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {promocionesVigentes.map(promo => (
                    <PromocionesTarjeta 
                        key={promo.id}
                        promocion={promo}
                        tiempoRestante={tiemposRestantes[promo.id]}
                    />
                ))}
            </div>
        </div>
    );
};

const PromocionesTarjeta = ({ promocion, tiempoRestante }) => {
    const esLastMinute = promocion.tipo === 'LAST_MINUTE';
    const esRetoque = promocion.tipo === 'RETOQUE';

    return (
        <div className={`
            relative p-5 rounded-xl shadow-xl overflow-hidden
            transform transition-all hover:scale-105 hover:shadow-2xl
            ${esLastMinute 
                ? 'bg-gradient-to-br from-red-500 via-rose-500 to-pink-600 text-white' 
                : 'bg-gradient-to-br from-purple-500 via-indigo-500 to-blue-600 text-white'
            }
        `}>
            {/* Animación de brillo para Last Minute */}
            {esLastMinute && (
                <div className="absolute inset-0 animate-pulse opacity-20 bg-white"></div>
            )}

            {/* Badge de tipo */}
            <div className="absolute top-3 right-3 z-10">
                <span className={`
                    text-xs font-bold px-3 py-1 rounded-full
                    shadow-lg transform transition-all
                    ${esLastMinute 
                        ? 'bg-white text-red-600 animate-bounce' 
                        : 'bg-white text-purple-600'
                    }
                `}>
                    {esLastMinute ? '⏰ LAST MINUTE' : '🎁 RETOQUE'}
                </span>
            </div>

            {/* Contenido */}
            <div className="relative z-20 pr-24">
                <h3 className="text-lg font-bold mb-2 drop-shadow-lg">
                    {promocion.nombre}
                </h3>
                
                <p className="text-sm opacity-95 mb-3 drop-shadow">
                    {promocion.descripcion}
                </p>

                {/* Descuento destacado */}
                <div className="mb-4 p-3 rounded-lg bg-white bg-opacity-25 backdrop-blur-sm border border-white border-opacity-30">
                    <div className="text-4xl font-bold drop-shadow-lg">
                        {promocion.descuento_porcentaje}%
                    </div>
                    <div className="text-xs opacity-95 drop-shadow">de descuento</div>
                </div>

                {/* Información específica por tipo */}
                {esLastMinute && tiempoRestante?.vigente && (
                    <div className="bg-white bg-opacity-20 backdrop-blur-sm rounded-lg p-3 mb-3 border border-white border-opacity-30">
                        <div className="text-xs opacity-95 mb-2">⏱️ Válido por:</div>
                        <div className="font-mono text-2xl font-bold drop-shadow-lg">
                            {String(tiempoRestante.horas).padStart(2, '0')}:
                            {String(tiempoRestante.minutos).padStart(2, '0')}:
                            {String(tiempoRestante.segundos).padStart(2, '0')}
                        </div>
                        <div className="text-xs opacity-75 mt-1">¡Solo por hoy!</div>
                    </div>
                )}

                {esRetoque && (
                    <div className="bg-white bg-opacity-20 backdrop-blur-sm rounded-lg p-3 mb-3 border border-white border-opacity-30">
                        <div className="text-xs opacity-95">
                            💄 Pack especial para tu próximo retoque
                        </div>
                    </div>
                )}

                {/* Servicios incluidos */}
                {promocion.servicios_count > 0 && (
                    <div className="text-xs opacity-90 mb-3 drop-shadow">
                        <span className="font-semibold">{promocion.servicios_count}</span> servicio(s) incluido(s)
                    </div>
                )}

                {/* Productos incluidos */}
                {promocion.productos_count > 0 && (
                    <div className="text-xs opacity-90 mb-3 drop-shadow">
                        <span className="font-semibold">{promocion.productos_count}</span> producto(s) incluido(s)
                    </div>
                )}

                {/* Botón de acción */}
                <button className={`
                    w-full mt-4 py-3 rounded-lg font-bold text-sm
                    transition-all transform hover:scale-105 active:scale-95
                    shadow-lg drop-shadow-xl
                    ${esLastMinute 
                        ? 'bg-white text-red-600 hover:bg-red-50 hover:shadow-red-300/50' 
                        : 'bg-white text-purple-600 hover:bg-purple-50 hover:shadow-purple-300/50'
                    }
                `}>
                    {esLastMinute ? '⚡ Agendar Ahora' : '📅 Ver Servicio'}
                </button>
            </div>

            {/* Decoración de fondo - Reloj para Last Minute */}
            {esLastMinute && (
                <div className="absolute bottom-0 right-0 opacity-15 pointer-events-none">
                    <svg width="140" height="140" viewBox="0 0 24 24" fill="currentColor" className="animate-spin-slow">
                        <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 18c-4.41 0-8-3.59-8-8s3.59-8 8-8 8 3.59 8 8-3.59 8-8 8zm.5-13H11v6l5.25 3.15.75-1.23-4.5-2.67z" />
                    </svg>
                </div>
            )}

            {/* Decoración de fondo - Caja de regalo para Retoque */}
            {esRetoque && (
                <div className="absolute bottom-0 right-0 opacity-15 pointer-events-none">
                    <svg width="140" height="140" viewBox="0 0 24 24" fill="currentColor">
                        <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 18c-4.41 0-8-3.59-8-8s3.59-8 8-8 8 3.59 8 8-3.59 8-8 8zm3.5-9c.83 0 1.5-.67 1.5-1.5S16.33 8 15.5 8 14 8.67 14 9.5s.67 1.5 1.5 1.5zm-7 0c.83 0 1.5-.67 1.5-1.5S9.33 8 8.5 8 7 8.67 7 9.5 7.67 11 8.5 11zm3.5 6.5c2.33 0 4.31-1.46 5.11-3.5H6.89c.8 2.04 2.78 3.5 5.11 3.5z" />
                    </svg>
                </div>
            )}
        </div>
    );
};

export default PromocionesCarte;
