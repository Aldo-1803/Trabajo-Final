import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { useNavigate } from 'react-router-dom'; // Importamos para redirigir al detalle
import jsPDF from 'jspdf';

const CatalogoRutinas = () => {
  const [rutinas, setRutinas] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [asignando, setAsignando] = useState(false);
  const [successMessage, setSuccessMessage] = useState('');
  const navigate = useNavigate();

  useEffect(() => {
    fetchRutinas();
  }, []);

  const fetchRutinas = async () => {
    setLoading(true);
    const token = localStorage.getItem('access_token');
    const headers = { Authorization: `Bearer ${token}` };

    try {
        console.log("🔄 Intentando obtener rutinas...");
        
        // Intentamos primero con localhost (que es lo que usabas antes)
        const response = await axios.get('http://localhost:8000/api/gestion/rutinas/', { headers });
        
        console.log("✅ Respuesta del Servidor:", response.data);

        // Lógica robusta para detectar la lista
        let data = [];
        if (Array.isArray(response.data)) {
            data = response.data;
        } else if (response.data && Array.isArray(response.data.results)) {
            data = response.data.results; // Caso Paginación
        }

        console.log("📦 Rutinas procesadas:", data);
        setRutinas(data);
        setError('');

    } catch (err) {
        console.error("❌ Error inicial:", err);
        setError('Error de conexión. Revisa la consola (F12).');
    } finally {
        setLoading(false);
    }
  };

  const handleSeleccionarRutina = async (e, rutinaId) => {
    e.stopPropagation(); // Evitar que el clic dispare la navegación al detalle
    try {
      setAsignando(true);
      const token = localStorage.getItem('access_token');
      
      // Usando la ruta correcta del ViewSet
      const response = await axios.post(
        'http://localhost:8000/api/gestion/rutinas/seleccionar/', 
        { rutina_id: rutinaId },
        { headers: { Authorization: `Bearer ${token}` } }
      );

      console.log("✅ Respuesta al agregar rutina:", response.data);
      setSuccessMessage('¡Rutina asignada exitosamente!');
      setTimeout(() => setSuccessMessage(''), 3000);
      fetchRutinas();
    } catch (err) {
      console.error('Error al asignar rutina:', err);
      setError(err.response?.data?.error || 'Error al asignar la rutina');
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

  if (loading) return <div className="text-center py-20 text-gray-500 font-bold">Cargando rutinas...</div>;

  return (
    <div className="min-h-screen bg-gray-50 p-8">
      <div className="max-w-7xl mx-auto">
        {/* Header */}
        <div className="mb-10 text-center">
          <h1 className="text-4xl font-bold text-gray-800 mb-2">Catálogo de Rutinas</h1>
          <p className="text-gray-500">Explora nuestras rutinas diseñadas por expertos.</p>
        </div>

        {/* Mensajes */}
        {error && (
          <div className="mb-6 p-4 bg-red-100 border-l-4 border-red-500 text-red-700 rounded shadow-sm">
            {error}
          </div>
        )}
        
        {successMessage && (
          <div className="mb-6 p-4 bg-green-100 border-l-4 border-green-500 text-green-700 rounded shadow-sm">
            {successMessage}
          </div>
        )}

        {/* Grid de Rutinas (Simplificado) */}
        {!Array.isArray(rutinas) || rutinas.length === 0 ? (
          <div className="text-center py-12 bg-white rounded-xl shadow-sm">
            <p className="text-gray-400 text-lg">No hay rutinas disponibles en este momento.</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8">
            {rutinas.map((rutina) => (
              <div
                key={rutina.id}
                onClick={() => navigate(`/rutina/${rutina.id}`)} // Navegar al detalle al hacer clic en la tarjeta
                className="bg-white rounded-xl shadow-md hover:shadow-xl transition-all duration-300 overflow-hidden border border-gray-100 cursor-pointer group flex flex-col h-full"
              >
                {/* Cabecera Colorida */}
                <div className="h-2 bg-gradient-to-r from-pink-500 to-rose-400"></div>
                
                <div className="p-6 flex-1 flex flex-col">
                  {/* Título y Objetivo */}
                  <div className="mb-4">
                    <h2 className="text-xl font-bold text-gray-800 group-hover:text-pink-600 transition-colors">
                        {rutina.nombre}
                    </h2>
                    <p className="text-sm text-gray-500 mt-2 font-medium italic">
                        {rutina.objetivo}
                    </p>
                  </div>

                  {/* Descripción Corta (Truncada) */}
                  <p className="text-gray-600 text-sm mb-6 line-clamp-2 flex-1">
                    {rutina.descripcion}
                  </p>

                  {/* Footer de la Tarjeta */}
                  <div className="mt-auto">
                      <div className="flex justify-between items-center mb-4 text-xs text-gray-400 font-semibold uppercase tracking-wide">
                          <span>v{rutina.version || 1}</span>
                          <span>{rutina.pasos ? `${rutina.pasos.length} Pasos` : 'Sin pasos'}</span>
                      </div>

                      {/* Botones de Acción */}
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          handleSeleccionarRutina(e, rutina.id);
                        }}
                        className="w-full py-2 bg-gray-100 hover:bg-pink-50 text-gray-600 hover:text-pink-600 rounded-lg font-bold text-sm transition-colors mb-2"
                      >
                        Agregar a Mis Rutinas
                      </button>

                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          handleDescargarRutina(rutina);
                        }}
                        className="w-full py-2 bg-gray-100 hover:bg-blue-50 text-gray-600 hover:text-blue-600 rounded-lg font-bold text-sm transition-colors"
                      >
                        Descargar PDF
                      </button>
                      
                      <div className="text-center text-pink-500 font-bold text-sm group-hover:underline">
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