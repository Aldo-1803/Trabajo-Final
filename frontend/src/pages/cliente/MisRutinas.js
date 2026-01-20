import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { confirmarAccion, notify } from '../../utils/notificaciones';

const MisRutinas = () => {
  const [rutinas, setRutinas] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [expandedRutina, setExpandedRutina] = useState(null);
  const [actualizando, setActualizando] = useState(null);
  const [successMessage, setSuccessMessage] = useState('');

  // 1. Definimos la función antes de usarla en useEffect para evitar errores de referencia
  const fetchRutinas = async () => {
    try {
      setLoading(true);
      const token = localStorage.getItem('access_token');
      const response = await axios.get('http://localhost:8000/api/gestion/rutinas-cliente/', {
        headers: { Authorization: `Bearer ${token}` }
      });
      
      const data = Array.isArray(response.data) ? response.data : response.data.results || [];
      setRutinas(data);
      setError('');
    } catch (err) {
      console.error('Error al cargar rutinas:', err);
      setError('No se pudieron cargar tus rutinas');
    } finally {
      setLoading(false);
    }
  };

  // 2. useEffect llama a la función ya definida
  useEffect(() => {
    fetchRutinas();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleDescargarArchivo = (rutina) => {
    if (!rutina.archivo) {
      setError('Esta rutina no tiene archivo adjunto');
      return;
    }
    // Abre el archivo en una nueva pestaña o lo descarga
    window.open(rutina.archivo, '_blank');
  };

  const handleActualizarRutina = async (rutinaId) => {
    try {
      setActualizando(rutinaId);
      const token = localStorage.getItem('access_token');
      
      const response = await axios.post(
        `http://localhost:8000/api/gestion/rutinas-cliente/${rutinaId}/actualizar_desde_original/`,
        {},
        { headers: { Authorization: `Bearer ${token}` } }
      );

      setRutinas(rutinas.map(r => r.id === rutinaId ? response.data : r));
      
      setSuccessMessage('¡Rutina actualizada exitosamente!');
      setTimeout(() => setSuccessMessage(''), 3000);
    } catch (err) {
      console.error('Error al actualizar rutina:', err);
      setError('Error al actualizar la rutina');
    } finally {
      setActualizando(null);
    }
  };

  const handleEliminarRutina = async (rutinaId, rutinaNombre) => {
    const result = await confirmarAccion({
      title: "¿Dejar de usar rutina?",
      text: `Se eliminará "${rutinaNombre}" de tus rutinas`,
      confirmButtonText: "Sí, eliminar"
    });
    if (!result.isConfirmed) return;

    try {
      const token = localStorage.getItem('access_token');
      
      await axios.delete(
        `http://localhost:8000/api/gestion/rutinas-cliente/${rutinaId}/`,
        { headers: { Authorization: `Bearer ${token}` } }
      );

      setRutinas(rutinas.filter(r => r.id !== rutinaId));
      notify.success('¡Rutina eliminada de tus rutinas!');
    } catch (err) {
      console.error('Error al eliminar rutina:', err);
      notify.error('Error al eliminar la rutina');
    }
  };

  // Sistema de archivo - ya no necesitamos generar PDF dinámicamente
  // El archivo está almacenado en el servidor

  if (loading) {
    return <div className="text-center py-8">Cargando tus rutinas...</div>;
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-[#F5EBE0] to-[#E3D5CA] p-8">
      <div className="max-w-4xl mx-auto">
        {/* Header */}
        <div className="mb-12">
          <h1 className="text-4xl font-bold text-[#817773] mb-3">Mis Rutinas de Cuidado</h1>
          <p className="text-[#AB9A91]">Sigue tus rutinas personalizadas de cuidado capilar</p>
        </div>

        {/* Mensajes */}
        {error && (
          <div className="mb-6 p-4 bg-red-100 border border-red-400 text-red-700 rounded-lg">
            {error}
          </div>
        )}
        
        {successMessage && (
          <div className="mb-6 p-4 bg-green-100 border border-green-400 text-green-700 rounded-lg">
            {successMessage}
          </div>
        )}

        {/* Lista de Rutinas */}
        {rutinas.length === 0 ? (
          <div className="bg-white rounded-xl shadow-lg p-12 text-center">
            <p className="text-[#AB9A91] text-lg mb-4">Aún no tienes rutinas asignadas</p>
            <a href="/catalogo-rutinas" className="text-[#D5BDAF] font-semibold hover:text-[#AB9A91]">
              Ver catálogo de rutinas →
            </a>
          </div>
        ) : (
          <div className="space-y-6">
            {rutinas.map((rutina) => (
              <div key={rutina.id}>


                {/* Tarjeta visible */}
                <div className="bg-white rounded-xl shadow-lg overflow-hidden border-l-4 border-[#D5BDAF] hover:shadow-xl transition-shadow">
                  {/* Header */}
                  <div 
                    className="bg-gradient-to-r from-[#E3D5CA] to-[#D5BDAF] p-6 cursor-pointer hover:from-[#D5BDAF] hover:to-[#AB9A91] transition-all"
                    onClick={() => setExpandedRutina(expandedRutina === rutina.id ? null : rutina.id)}
                  >
                    <div className="flex justify-between items-start">
                      <div>
                        <h2 className="text-2xl font-bold text-[#817773]">{rutina.nombre}</h2>
                        <p className="text-[#AB9A91] mt-1">{rutina.objetivo}</p>
                      </div>
                      <div className="text-right">
                        <span className={`inline-block px-4 py-2 rounded-full text-sm font-semibold ${
                          rutina.estado === 'activa' 
                            ? 'bg-green-100 text-green-700'
                            : rutina.estado === 'desactualizada'
                            ? 'bg-yellow-100 text-yellow-700'
                            : 'bg-red-100 text-red-700'
                        }`}>
                          {rutina.estado_display}
                        </span>
                      </div>
                    </div>
                  </div>

                  {/* Contenido Expandible */}
                  {expandedRutina === rutina.id && (
                    <div className="p-6 border-t border-[#E3D5CA]">
                      {/* Descripción */}
                      <p className="text-[#AB9A91] mb-6">{rutina.descripcion}</p>

                      {/* Alert de Actualización */}
                      {rutina.descargar_notificacion && rutina.estado === 'desactualizada' && (
                        <div className="mb-6 p-4 bg-yellow-50 border-l-4 border-yellow-400 rounded">
                          <p className="text-yellow-800 font-semibold mb-3">
                            Nueva versión disponible (v{rutina.version_asignada + 1})
                          </p>
                          <button
                            onClick={() => handleActualizarRutina(rutina.id)}
                            disabled={actualizando === rutina.id}
                            className="bg-yellow-400 hover:bg-yellow-500 text-yellow-900 font-semibold py-2 px-4 rounded transition-colors"
                          >
                            {actualizando === rutina.id ? 'Actualizando...' : 'Actualizar Ahora'}
                          </button>
                        </div>
                      )}

                      {/* Archivo de Rutina */}
                      <div>
                        <h3 className="font-bold text-[#817773] mb-4 text-lg">📄 Archivo de la Rutina:</h3>
                        {rutina.archivo ? (
                          <div className="p-4 rounded-lg border-2 bg-[#F5EBE0] border-[#D5BDAF]">
                            <p className="text-sm text-[#AB9A91] mb-3">Tu rutina personalizada está lista para descargar</p>
                            <button
                              onClick={() => handleDescargarArchivo(rutina)}
                              className="bg-[#D5BDAF] hover:bg-[#AB9A91] text-white font-semibold py-2 px-4 rounded transition-colors flex items-center gap-2"
                            >
                              📥 Abrir/Descargar Rutina
                            </button>
                          </div>
                        ) : (
                          <div className="p-4 rounded-lg border-2 bg-yellow-50 border-yellow-200">
                            <p className="text-sm text-yellow-800">Archivo no disponible</p>
                          </div>
                        )}
                      </div>

                      {/* Info y Botones */}
                      <div className="mt-6 pt-6 border-t border-[#E3D5CA]">
                        <div className="flex justify-between items-center mb-4">
                          <div className="text-sm text-[#AB9A91]">
                            <p>Versión: <span className="font-semibold">v{rutina.version_asignada}</span></p>
                            <p>Asignada: <span className="font-semibold">{new Date(rutina.fecha_asignacion).toLocaleDateString()}</span></p>
                          </div>
                        </div>
                        
                        <div className="flex gap-3">
                          <button
                            onClick={() => handleDescargarArchivo(rutina)}
                            className="flex-1 bg-[#D5BDAF] hover:bg-[#AB9A91] text-white font-semibold py-2 px-4 rounded transition-colors flex items-center justify-center gap-2"
                          >
                            📥 Descargar Rutina
                          </button>
                          <button
                            onClick={() => handleEliminarRutina(rutina.id, rutina.nombre)}
                            className="flex-1 bg-red-500 hover:bg-red-600 text-white font-semibold py-2 px-4 rounded transition-colors flex items-center justify-center gap-2"
                          >
                            🗑️ Dejar de Usar
                          </button>
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

export default MisRutinas;