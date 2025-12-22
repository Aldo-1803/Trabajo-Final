import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';

const CatalogoServicios = () => {
  const [servicios, setServicios] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const navigate = useNavigate();

  useEffect(() => {
    fetchServicios();
  }, []);

  const fetchServicios = async () => {
    setLoading(true);
    const token = localStorage.getItem('access_token');
    const headers = { Authorization: `Bearer ${token}` };

    try {
      const response = await axios.get('http://127.0.0.1:8000/api/gestion/servicios/', { headers });
      
      let data = [];
      if (Array.isArray(response.data)) {
        data = response.data;
      } else if (response.data && Array.isArray(response.data.results)) {
        data = response.data.results;
      }

      setServicios(data.filter(s => s.activo)); // Solo servicios activos
      setError('');
    } catch (err) {
      console.error("Error al cargar servicios:", err);
      setError('Error al cargar los servicios disponibles.');
    } finally {
      setLoading(false);
    }
  };

  const handleVerDetalle = (servicioId) => {
    navigate(`/servicio/${servicioId}`);
  };

  if (loading) return (
    <div className="min-h-screen p-6" style={{ backgroundColor: '#F5EBE0' }}>
      <div className="max-w-6xl mx-auto">
        <div className="text-center" style={{ color: '#8B8682' }}>Cargando servicios...</div>
      </div>
    </div>
  );

  return (
    <div className="min-h-screen p-6" style={{ backgroundColor: '#F5EBE0' }}>
      <div className="max-w-6xl mx-auto">
        
        {/* HEADER */}
        <div className="flex justify-between items-center mb-8">
          <div>
            <h1 className="text-3xl font-bold" style={{ color: '#817773' }}>Nuestros Servicios</h1>
            <p style={{ color: '#8B8682' }}>Descubre todos los servicios capilares que ofrecemos</p>
          </div>
          <button 
            onClick={() => navigate('/perfil')}
            className="font-bold transition px-4 py-2 rounded-lg"
            style={{ color: '#817773', backgroundColor: '#E3D5CA' }}
            onMouseEnter={(e) => e.target.style.backgroundColor = '#D5BDAF'}
            onMouseLeave={(e) => e.target.style.backgroundColor = '#E3D5CA'}
          >
            ← Volver
          </button>
        </div>

        {error && (
          <div className="mb-6 p-4 rounded shadow-sm border-l-4" style={{ backgroundColor: '#FFE8E8', borderColor: '#C73E3E', color: '#C73E3E' }}>
            {error}
          </div>
        )}

        {/* GRID DE SERVICIOS */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {servicios.length === 0 ? (
            <div className="col-span-full text-center py-12 rounded-xl shadow" style={{ backgroundColor: 'white', color: '#8B8682' }}>
              <p className="text-lg">No hay servicios disponibles en este momento.</p>
            </div>
          ) : (
            servicios.map((servicio) => (
              <div 
                key={servicio.id}
                className="rounded-xl shadow-md overflow-hidden border-t-4 hover:shadow-lg transition-shadow cursor-pointer"
                style={{ backgroundColor: 'white', borderColor: '#D5BDAF' }}
                onClick={() => handleVerDetalle(servicio.id)}
              >
                {/* ENCABEZADO CON GRADIENTE */}
                <div 
                  className="p-6"
                  style={{ background: 'linear-gradient(135deg, #D5BDAF 0%, #AB9A91 100%)' }}
                >
                  <h3 className="text-xl font-bold text-white">{servicio.nombre}</h3>
                  {servicio.categoria_nombre && (
                    <p className="text-xs mt-1" style={{ color: '#F5EBE0' }}>{servicio.categoria_nombre}</p>
                  )}
                </div>

                {/* CONTENIDO */}
                <div className="p-6">
                  {servicio.descripcion && (
                    <p className="text-sm mb-4 line-clamp-2" style={{ color: '#5A5451' }}>
                      {servicio.descripcion}
                    </p>
                  )}

                  {/* INFORMACIÓN */}
                  <div className="space-y-2 mb-4 border-t border-b" style={{ borderColor: '#E3D5CA', paddingTop: '1rem', paddingBottom: '1rem' }}>
                    {servicio.precio_base && (
                      <div className="flex justify-between items-center">
                        <span style={{ color: '#8B8682' }}>Precio:</span>
                        <span className="font-bold text-lg" style={{ color: '#2E7D2E' }}>
                          ${parseFloat(servicio.precio_base).toLocaleString('es-AR')}
                        </span>
                      </div>
                    )}
                    {servicio.duracion_estimada && (
                      <div className="flex justify-between items-center">
                        <span style={{ color: '#8B8682' }}>Duración:</span>
                        <span className="font-bold" style={{ color: '#817773' }}>
                          {servicio.duracion_estimada} minutos
                        </span>
                      </div>
                    )}
                  </div>

                  {/* BOTÓN VER DETALLE */}
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      handleVerDetalle(servicio.id);
                    }}
                    className="w-full py-2 rounded-lg font-bold transition text-white"
                    style={{ backgroundColor: '#AB9A91' }}
                    onMouseEnter={(e) => e.target.style.backgroundColor = '#817773'}
                    onMouseLeave={(e) => e.target.style.backgroundColor = '#AB9A91'}
                  >
                    Ver Detalle
                  </button>
                </div>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
};

export default CatalogoServicios;
