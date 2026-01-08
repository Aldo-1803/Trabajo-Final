import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { useNavigate } from 'react-router-dom'; // Importamos para redirigir al detalle
import jsPDF from 'jspdf';

const CatalogoRutinas = () => {
  const [rutinas, setRutinas] = useState([]);
  const [misRutinas, setMisRutinas] = useState([]); // Rutinas ya asignadas
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [asignando, setAsignando] = useState(false);
  const [successMessage, setSuccessMessage] = useState('');
  const navigate = useNavigate();

  useEffect(() => {
    fetchRutinas();
    fetchMisRutinas(); // Cargar las rutinas que ya tiene el cliente
  }, []);

  const fetchRutinas = async () => {
    setLoading(true);
    const token = localStorage.getItem('access_token');
    const headers = { Authorization: `Bearer ${token}` };

    try {
        // Intentamos primero con localhost (que es lo que usabas antes)
        const response = await axios.get('http://localhost:8000/api/gestion/rutinas/', { headers });
        // Lógica robusta para detectar la lista
        let data = [];
        if (Array.isArray(response.data)) {
            data = response.data;
        } else if (response.data && Array.isArray(response.data.results)) {
            data = response.data.results; // Caso Paginación
        }
        setRutinas(data);
        setError('');

    } catch (err) {
        console.error("❌ Error inicial:", err);
        setError('Error de conexión. Revisa la consola (F12).');
    } finally {
        setLoading(false);
    }
  };

  const fetchMisRutinas = async () => {
    const token = localStorage.getItem('access_token');
    const headers = { Authorization: `Bearer ${token}` };

    try {
        const response = await axios.get('http://localhost:8000/api/gestion/rutinas-cliente/', { headers });
        
        let data = [];
        if (Array.isArray(response.data)) {
            data = response.data;
        } else if (response.data && Array.isArray(response.data.results)) {
            data = response.data.results;
        }

        setMisRutinas(data);
    } catch (err) {
        console.error("❌ Error al cargar mis rutinas:", err);
        // Si hay error, simplemente continuamos sin las rutinas del cliente
    }
  };

  const handleSeleccionarRutina = async (e, rutinaId) => {
    e.stopPropagation(); // Evitar que el clic dispare la navegación al detalle
    
    // Verificar si ya tiene la rutina asignada comparando con rutina_original
    const yaAsignada = misRutinas.some(r => r.rutina_original === rutinaId);
    if (yaAsignada) {
      setError('❌ Esta rutina ya está en "Mis Rutinas". No puedes asignarla nuevamente.');
      setTimeout(() => setError(''), 4000);
      return;
    }

    try {
      setAsignando(true);
      const token = localStorage.getItem('access_token');
      
      // Usando la ruta correcta del ViewSet
      const response = await axios.post(
        'http://localhost:8000/api/gestion/rutinas/seleccionar/', 
        { rutina_id: rutinaId },
        { headers: { Authorization: `Bearer ${token}` } }
      );
      setSuccessMessage('✅ ¡Rutina asignada exitosamente!');
      setTimeout(() => setSuccessMessage(''), 3000);
      fetchRutinas();
      fetchMisRutinas(); // Actualizar lista de mis rutinas
    } catch (err) {
      console.error('Error al asignar rutina:', err);
      if (err.response?.status === 400) {
        setError('⚠️ Esta rutina ya la tienes asignada.');
      } else {
        setError(err.response?.data?.error || 'Error al asignar la rutina');
      }
    } finally {
      setAsignando(false);
    }
  };

  const handleDescargarRutina = (rutina) => {
    const doc = new jsPDF();
    doc.setFontSize(16);
    doc.text(rutina.nombre, 10, 10);
    doc.setFontSize(12);
    doc.text(`Objetivo: ${rutina.objetivo}`, 10, 20);
    doc.text(`Descripción: ${rutina.descripcion}`, 10, 30);

    if (rutina.pasos && rutina.pasos.length > 0) {
      doc.text('Pasos:', 10, 40);
      rutina.pasos.forEach((paso, index) => {
        doc.text(`${index + 1}. ${paso.descripcion}`, 10, 50 + index * 10);
      });
    } else {
      doc.text('Sin pasos definidos.', 10, 40);
    }

    doc.save(`${rutina.nombre}.pdf`);
  };

  if (loading) return <div className="text-center py-20 font-bold" style={{ color: '#8B8682', backgroundColor: '#F5EBE0', minHeight: '100vh' }}>Cargando rutinas...</div>;

  return (
    <div className="min-h-screen p-8" style={{ backgroundColor: '#F5EBE0' }}>
      <div className="max-w-7xl mx-auto">
        {/* Header */}
        <div className="mb-10 text-center">
          <h1 className="text-4xl font-bold mb-2" style={{ color: '#817773' }}>Catálogo de Rutinas</h1>
          <p style={{ color: '#8B8682' }}>Explora nuestras rutinas diseñadas por expertos.</p>
        </div>

        {/* Mensajes */}
        {error && (
          <div className="mb-6 p-4 rounded shadow-sm border-l-4" style={{ backgroundColor: '#FFE8E8', borderColor: '#C73E3E', color: '#C73E3E' }}>
            {error}
          </div>
        )}
        
        {successMessage && (
          <div className="mb-6 p-4 rounded shadow-sm border-l-4" style={{ backgroundColor: '#E8F5E8', borderColor: '#2E7D2E', color: '#2E7D2E' }}>
            {successMessage}
          </div>
        )}

        {/* Grid de Rutinas (Simplificado) */}
        {!Array.isArray(rutinas) || rutinas.length === 0 ? (
          <div className="text-center py-12 rounded-xl shadow-sm" style={{ backgroundColor: 'white' }}>
            <p style={{ color: '#8B8682' }} className="text-lg">No hay rutinas disponibles en este momento.</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8">
            {rutinas.map((rutina) => (
              <div
                key={rutina.id}
                onClick={() => navigate(`/rutina/${rutina.id}`)}
                className="rounded-xl shadow-md hover:shadow-xl transition-all duration-300 overflow-hidden border cursor-pointer group flex flex-col h-full"
                style={{ backgroundColor: 'white', borderColor: '#E3D5CA' }}
              >
                {/* Cabecera Colorida */}
                <div style={{ background: 'linear-gradient(135deg, #D5BDAF 0%, #AB9A91 100%)', height: '8px' }}></div>
                
                <div className="p-6 flex-1 flex flex-col">
                  {/* Título y Objetivo */}
                  <div className="mb-4">
                    <h2 className="text-xl font-bold transition-colors" style={{ color: '#817773' }}>
                        {rutina.nombre}
                    </h2>
                    <p className="text-sm mt-2 font-medium italic" style={{ color: '#8B8682' }}>
                        {rutina.objetivo}
                    </p>
                  </div>

                  {/* Descripción Corta (Truncada) */}
                  <p className="text-sm mb-6 line-clamp-2 flex-1" style={{ color: '#5A5451' }}>
                    {rutina.descripcion}
                  </p>

                  {/* Footer de la Tarjeta */}
                  <div className="mt-auto">
                      <div className="flex justify-between items-center mb-4 text-xs font-semibold uppercase tracking-wide" style={{ color: '#ABA89E' }}>
                          <span>v{rutina.version || 1}</span>
                          <span>{rutina.pasos ? `${rutina.pasos.length} Pasos` : 'Sin pasos'}</span>
                      </div>

                      {/* Botones de Acción */}
                      {misRutinas.some(r => r.rutina_original === rutina.id) ? (
                        <button
                          disabled
                          className="w-full py-2 rounded-lg font-bold text-sm cursor-not-allowed opacity-75 mb-2"
                          style={{ backgroundColor: '#E8F5E8', color: '#2E7D2E' }}
                        >
                          ✓ Ya está en Mis Rutinas
                        </button>
                      ) : (
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            handleSeleccionarRutina(e, rutina.id);
                          }}
                          disabled={asignando}
                          className="w-full py-2 rounded-lg font-bold text-sm transition-colors mb-2 disabled:opacity-50"
                          style={{ backgroundColor: '#E3D5CA', color: '#817773' }}
                          onMouseEnter={(e) => e.target.style.backgroundColor = '#D5BDAF'}
                          onMouseLeave={(e) => e.target.style.backgroundColor = '#E3D5CA'}
                        >
                          {asignando ? 'Guardando...' : 'Agregar a Mis Rutinas'}
                        </button>
                      )}

                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          handleDescargarRutina(rutina);
                        }}
                        className="w-full py-2 rounded-lg font-bold text-sm transition-colors"
                        style={{ backgroundColor: '#E3D5CA', color: '#817773' }}
                        onMouseEnter={(e) => e.target.style.backgroundColor = '#D5BDAF'}
                        onMouseLeave={(e) => e.target.style.backgroundColor = '#E3D5CA'}
                      >
                        Descargar PDF
                      </button>
                      
                      <div className="text-center font-bold text-sm group-hover:underline mt-2" style={{ color: '#AB9A91' }}>
                          Ver detalle completo →
                      </div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

export default CatalogoRutinas;