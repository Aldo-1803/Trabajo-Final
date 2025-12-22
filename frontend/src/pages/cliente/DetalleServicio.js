import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { useNavigate, useParams } from 'react-router-dom';

const DetalleServicio = () => {
  const { servicioId } = useParams();
  const [servicio, setServicio] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const navigate = useNavigate();

  useEffect(() => {
    fetchDetalleServicio();
  }, [servicioId]);

  const fetchDetalleServicio = async () => {
    setLoading(true);
    const token = localStorage.getItem('access_token');
    const headers = { Authorization: `Bearer ${token}` };

    try {
      const response = await axios.get(
        `http://127.0.0.1:8000/api/gestion/servicios/${servicioId}/`,
        { headers }
      );
      setServicio(response.data);
      setError('');
    } catch (err) {
      console.error("Error al cargar detalle del servicio:", err);
      setError('Error al cargar los detalles del servicio.');
    } finally {
      setLoading(false);
    }
  };

  if (loading) return (
    <div className="min-h-screen p-6" style={{ backgroundColor: '#F5EBE0' }}>
      <div className="max-w-4xl mx-auto">
        <div className="text-center" style={{ color: '#8B8682' }}>Cargando detalle...</div>
      </div>
    </div>
  );

  if (!servicio) return (
    <div className="min-h-screen p-6" style={{ backgroundColor: '#F5EBE0' }}>
      <div className="max-w-4xl mx-auto">
        <div className="text-center" style={{ color: '#C73E3E' }}>Servicio no encontrado</div>
      </div>
    </div>
  );

  return (
    <div className="min-h-screen p-6" style={{ backgroundColor: '#F5EBE0' }}>
      <div className="max-w-4xl mx-auto">
        
        {/* BOTÓN VOLVER */}
        <button 
          onClick={() => navigate('/catalogo-servicios')}
          className="mb-6 font-bold transition px-4 py-2 rounded-lg"
          style={{ color: '#817773', backgroundColor: '#E3D5CA' }}
          onMouseEnter={(e) => e.target.style.backgroundColor = '#D5BDAF'}
          onMouseLeave={(e) => e.target.style.backgroundColor = '#E3D5CA'}
        >
          ← Volver al Catálogo
        </button>

        {error && (
          <div className="mb-6 p-4 rounded shadow-sm border-l-4" style={{ backgroundColor: '#FFE8E8', borderColor: '#C73E3E', color: '#C73E3E' }}>
            {error}
          </div>
        )}

        {/* TARJETA PRINCIPAL */}
        <div className="rounded-xl shadow-xl overflow-hidden border" style={{ backgroundColor: 'white', borderColor: '#D5D1CC' }}>
          
          {/* ENCABEZADO CON GRADIENTE */}
          <div 
            className="p-8"
            style={{ background: 'linear-gradient(135deg, #AB9A91 0%, #817773 100%)' }}
          >
            <h1 className="text-4xl font-bold text-white">{servicio.nombre}</h1>
            {servicio.categoria_nombre && (
              <p className="mt-2 text-lg" style={{ color: '#E3D5CA' }}>📁 {servicio.categoria_nombre}</p>
            )}
          </div>

          {/* CONTENIDO PRINCIPAL */}
          <div className="p-8">
            
            {/* DESCRIPCIÓN */}
            {servicio.descripcion && (
              <div className="mb-8">
                <h2 className="text-2xl font-bold mb-3" style={{ color: '#817773' }}>Descripción</h2>
                <p className="text-lg leading-relaxed" style={{ color: '#5A5451' }}>
                  {servicio.descripcion}
                </p>
              </div>
            )}

            {/* INFORMACIÓN DETALLADA */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
              
              {/* PRECIO */}
              {servicio.precio_base && (
                <div className="p-6 rounded-lg border-l-4" style={{ backgroundColor: '#E8F5E8', borderColor: '#2E7D2E' }}>
                  <p className="text-sm font-bold mb-2" style={{ color: '#8B8682' }}>Precio Base</p>
                  <p className="text-3xl font-bold" style={{ color: '#2E7D2E' }}>
                    ${parseFloat(servicio.precio_base).toLocaleString('es-AR')}
                  </p>
                </div>
              )}

              {/* DURACIÓN */}
              {servicio.duracion_estimada && (
                <div className="p-6 rounded-lg border-l-4" style={{ backgroundColor: '#E8D5CA', borderColor: '#AB9A91' }}>
                  <p className="text-sm font-bold mb-2" style={{ color: '#8B8682' }}>Duración Estimada</p>
                  <p className="text-3xl font-bold" style={{ color: '#817773' }}>
                    {servicio.duracion_estimada} min
                  </p>
                </div>
              )}

              {/* ESTADO */}
              <div className="p-6 rounded-lg border-l-4" style={{ backgroundColor: '#E8F0F5', borderColor: '#AB9A91' }}>
                <p className="text-sm font-bold mb-2" style={{ color: '#8B8682' }}>Estado</p>
                <p className="text-lg font-bold" style={{ color: '#817773' }}>
                  {servicio.activo ? '✓ Disponible' : 'No disponible'}
                </p>
              </div>
            </div>

            {/* IMPACTOS EN EL CABELLO */}
            <div className="border-t" style={{ borderColor: '#D5D1CC', paddingTop: '2rem' }}>
              <h2 className="text-2xl font-bold mb-6" style={{ color: '#817773' }}>Impacto en tu Cabello</h2>
              
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                
                {/* IMPACTO EN POROSIDAD */}
                {servicio.impacto_porosidad_nombre && (
                  <div className="p-6 rounded-lg" style={{ backgroundColor: '#F5EBE0', borderColor: '#E3D5CA', border: '2px solid #E3D5CA' }}>
                    <h3 className="font-bold mb-2" style={{ color: '#817773' }}>Impacto en Porosidad</h3>
                    <p className="text-lg" style={{ color: '#5A5451' }}>
                      {servicio.impacto_porosidad_nombre}
                    </p>
                  </div>
                )}

                {/* IMPACTO EN ESTADO */}
                {servicio.impacto_estado_nombre && (
                  <div className="p-6 rounded-lg" style={{ backgroundColor: '#F5EBE0', borderColor: '#E3D5CA', border: '2px solid #E3D5CA' }}>
                    <h3 className="font-bold mb-2" style={{ color: '#817773' }}>Impacto en Estado</h3>
                    <p className="text-lg" style={{ color: '#5A5451' }}>
                      {servicio.impacto_estado_nombre}
                    </p>
                  </div>
                )}
              </div>
            </div>

            {/* RUTINA RECOMENDADA */}
            {servicio.rutina_recomendada_nombre && (
              <div className="mt-8 p-6 rounded-lg border-l-4" style={{ backgroundColor: '#E3D5CA', borderColor: '#AB9A91' }}>
                <h3 className="font-bold mb-2" style={{ color: '#817773' }}>Rutina Recomendada</h3>
                <p className="text-lg" style={{ color: '#5A5451' }}>
                  {servicio.rutina_recomendada_nombre}
                </p>
              </div>
            )}

            {/* BOTONES DE ACCIÓN */}
            <div className="mt-8 flex gap-4">
              <button
                onClick={() => navigate('/agendar-turno')}
                className="flex-1 py-3 rounded-lg font-bold text-white transition"
                style={{ backgroundColor: '#AB9A91' }}
                onMouseEnter={(e) => e.target.style.backgroundColor = '#817773'}
                onMouseLeave={(e) => e.target.style.backgroundColor = '#AB9A91'}
              >
                Agendar este Servicio
              </button>
              <button
                onClick={() => navigate('/catalogo-servicios')}
                className="flex-1 py-3 rounded-lg font-bold transition"
                style={{ backgroundColor: '#E3D5CA', color: '#817773' }}
                onMouseEnter={(e) => e.target.style.backgroundColor = '#D5BDAF'}
                onMouseLeave={(e) => e.target.style.backgroundColor = '#E3D5CA'}
              >
                Ver Otros Servicios
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default DetalleServicio;
