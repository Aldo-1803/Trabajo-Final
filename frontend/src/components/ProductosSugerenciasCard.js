import React, { useState, useEffect } from 'react';
import axios from 'axios';

const ProductosSugerenciasCard = () => {
    const [productos, setProductos] = useState([]);
    const [motivoSugerencia, setMotivoSugerencia] = useState('');
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        cargarSugerencias();
    }, []);

    const cargarSugerencias = async () => {
        setLoading(true);
        try {
            const token = localStorage.getItem('access_token');
            const res = await axios.get('http://127.0.0.1:8000/api/gestion/productos/sugeridos-cliente/', {
                headers: { 'Authorization': `Bearer ${token}` }
            });
            
            setProductos(res.data.productos_sugeridos || []);
            setMotivoSugerencia(res.data.motivo_sugerencia);
        } catch (error) {
            // Sin diagnóstico previo, simplemente no mostrar nada
            setProductos([]);
        } finally {
            setLoading(false);
        }
    };

    if (loading) {
        return <div style={{ color: '#8B8682' }}>Cargando sugerencias...</div>;
    }

    if (productos.length === 0) {
        return (
            <div className="p-4 rounded-lg border" style={{ backgroundColor: '#F5EBE0', borderColor: '#D5D1CC' }}>
                <p style={{ color: '#8B8682' }} className="text-sm">
                    💡 Realiza un diagnóstico capilar para recibir recomendaciones personalizadas de productos
                </p>
            </div>
        );
    }

    return (
        <div className="p-4 rounded-lg border" style={{ backgroundColor: 'white', borderColor: '#D5D1CC' }}>
            <h3 className="font-bold mb-3" style={{ color: '#817773' }}>
                🌟 Productos Recomendados para Ti
            </h3>
            <p style={{ color: '#8B8682' }} className="text-sm mb-4">
                {motivoSugerencia}
            </p>
            
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
                {productos.slice(0, 6).map((producto) => (
                    <div 
                        key={producto.id}
                        className="p-3 rounded-lg text-center transition hover:shadow-md"
                        style={{ backgroundColor: '#F5EBE0' }}
                    >
                        {producto.imagen_url && (
                            <img 
                                src={producto.imagen_url} 
                                alt={producto.nombre}
                                className="w-full h-20 object-cover rounded mb-2"
                            />
                        )}
                        <p className="text-xs font-semibold" style={{ color: '#817773' }}>
                            {producto.nombre}
                        </p>
                        <p className="text-xs" style={{ color: '#2E7D2E' }}>
                            ${parseFloat(producto.precio).toLocaleString()}
                        </p>
                        <button 
                            className="mt-2 px-2 py-1 text-xs rounded font-bold text-white transition"
                            style={{ backgroundColor: '#AB9A91' }}
                            onMouseEnter={(e) => e.target.style.backgroundColor = '#817773'}
                            onMouseLeave={(e) => e.target.style.backgroundColor = '#AB9A91'}
                        >
                            Ver
                        </button>
                    </div>
                ))}
            </div>

            <button 
                className="w-full mt-4 py-2 rounded-lg font-bold text-white transition"
                style={{ backgroundColor: '#817773' }}
                onMouseEnter={(e) => e.target.style.backgroundColor = '#5A5451'}
                onMouseLeave={(e) => e.target.style.backgroundColor = '#817773'}
            >
                Ver todos los recomendados →
            </button>
        </div>
    );
};

export default ProductosSugerenciasCard;
