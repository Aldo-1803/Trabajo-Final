import React, { useState, useEffect } from 'react';
import axios from 'axios';
import jsPDF from 'jspdf';
import html2canvas from 'html2canvas';

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

  const handleMarcarPasoCompletado = async (rutinaId, pasoId) => {
    try {
      const token = localStorage.getItem('access_token');
      
      await axios.post(
        `http://localhost:8000/api/gestion/rutinas-cliente/${rutinaId}/marcar_paso_completado/`,
        { paso_id: pasoId },
        { headers: { Authorization: `Bearer ${token}` } }
      );

      setRutinas(rutinas.map(r => {
        if (r.id === rutinaId) {
          return {
            ...r,
            pasos: r.pasos.map(p =>
              p.id === pasoId ? { ...p, completado: true, fecha_completado: new Date().toISOString() } : p
            )
          };
        }
        return r;
      }));

      setSuccessMessage('Paso marcado como completado');
      setTimeout(() => setSuccessMessage(''), 2000);
    } catch (err) {
      console.error('Error al marcar paso:', err);
      setError('Error al marcar el paso como completado');
    }
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

  const descargarRutinaPDF = async (rutina) => {
    try {
      const element = document.getElementById(`rutina-pdf-${rutina.id}`);
      // Aseguramos que el elemento existe antes de intentar capturarlo
      if (!element) return;

      // Hacemos visible el elemento temporalmente si fuera necesario, 
      // aunque html2canvas suele poder renderizar elementos ocultos si están en el DOM.
      // Aquí confiamos en que 'display: none' no impida la lectura del DOM, 
      // pero a veces html2canvas requiere que el elemento tenga visibilidad o esté fuera de pantalla (position absolute negative).
      // Si tienes problemas con el PDF en blanco, cambia 'display: none' por una clase que lo mueva fuera del viewport.
      
      const canvas = await html2canvas(element, { scale: 2 });
      const imgData = canvas.toDataURL('image/png');
      
      const pdf = new jsPDF({
        orientation: 'portrait',
        unit: 'mm',
        format: 'a4'
      });
      
      const pageHeight = pdf.internal.pageSize.getHeight();
      const pageWidth = pdf.internal.pageSize.getWidth();
      const imgHeight = (canvas.height * pageWidth) / canvas.width;
      let heightLeft = imgHeight;
      let position = 0;
      
      pdf.addImage(imgData, 'PNG', 0, position, pageWidth, imgHeight);
      heightLeft -= pageHeight;
      
      while (heightLeft >= 0) {
        position = heightLeft - imgHeight;
        pdf.addPage();
        pdf.addImage(imgData, 'PNG', 0, position, pageWidth, imgHeight);
        heightLeft -= pageHeight;
      }
      
      pdf.save(`rutina-${rutina.nombre.replace(/\s+/g, '-')}.pdf`);
    } catch (err) {
      console.error('Error al generar PDF:', err);
      setError('Error al descargar la rutina en PDF');
    }
  };

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
                {/* Div oculto para captura PDF */}
                {/* NOTA: html2canvas a veces falla con display: none. 
                    Si el PDF sale en blanco, cambia style={{ display: 'none' }} 
                    por style={{ position: 'absolute', left: '-9999px', top: 0 }} */}
                <div id={`rutina-pdf-${rutina.id}`} style={{ position: 'absolute', left: '-9999px', top: 0, width: '800px' }}>
                  <div style={{ padding: '40px', backgroundColor: '#fff', fontFamily: 'Arial, sans-serif' }}>
                    <h1 style={{ fontSize: '32px', marginBottom: '10px', color: '#817773' }}>
                      {rutina.nombre}
                    </h1>
                    <p style={{ fontSize: '16px', color: '#AB9A91', marginBottom: '20px' }}>
                      {rutina.objetivo}
                    </p>
                    <p style={{ fontSize: '14px', color: '#666', marginBottom: '30px', lineHeight: '1.6' }}>
                      {rutina.descripcion}
                    </p>
                    
                    <h2 style={{ fontSize: '20px', marginBottom: '15px', color: '#817773' }}>
                      Pasos de la Rutina
                    </h2>
                    <div>
                      {rutina.pasos && rutina.pasos.map((paso) => (
                        <div key={paso.id} style={{ marginBottom: '15px', padding: '10px', backgroundColor: '#F5EBE0', borderRadius: '8px' }}>
                          <p style={{ fontSize: '14px', fontWeight: 'bold', color: '#817773', marginBottom: '5px' }}>
                            Paso {paso.orden}: {paso.titulo}
                          </p>
                          <p style={{ fontSize: '12px', color: '#666', marginBottom: '3px' }}>
                            {paso.descripcion}
                          </p>
                          <p style={{ fontSize: '12px', color: '#AB9A91' }}>
                            Frecuencia: {paso.frecuencia}
                          </p>
                        </div>
                      ))}
                    </div>
                    <div style={{ marginTop: '30px', paddingTop: '20px', borderTop: '1px solid #E3D5CA', fontSize: '12px', color: '#AB9A91' }}>
                      <p>Versión: v{rutina.version_asignada}</p>
                      <p>Asignada el: {new Date(rutina.fecha_asignacion).toLocaleDateString('es-ES')}</p>
                    </div>
                  </div>
                </div>

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

                      {/* Pasos */}
                      <div>
                        <h3 className="font-bold text-[#817773] mb-4 text-lg">Pasos de la Rutina:</h3>
                        <div className="space-y-3">
                          {rutina.pasos && rutina.pasos.map((paso) => (
                            <div
                              key={paso.id}
                              className={`p-4 rounded-lg border-2 transition-all ${
                                paso.completado
                                  ? 'bg-green-50 border-green-300'
                                  : 'bg-[#F5EBE0] border-[#D5BDAF]'
                              }`}
                            >
                              <div className="flex items-start gap-4">
                                <input
                                  type="checkbox"
                                  checked={paso.completado}
                                  onChange={() => handleMarcarPasoCompletado(rutina.id, paso.id)}
                                  disabled={paso.completado}
                                  className="w-6 h-6 rounded cursor-pointer mt-1 accent-green-600"
                                />
                                <div className="flex-1">
                                  <div className="flex justify-between items-start">
                                    <div>
                                      <p className={`font-semibold ${paso.completado ? 'line-through text-gray-500' : 'text-[#817773]'}`}>
                                        Paso {paso.orden}: {paso.titulo}
                                      </p>
                                      <p className="text-sm text-[#AB9A91] mt-1">
                                        {paso.descripcion}
                                      </p>
                                      <p className="text-sm text-[#AB9A91] mt-1">
                                        Frecuencia: <span className="font-semibold">{paso.frecuencia}</span>
                                      </p>
                                    </div>
                                    {paso.completado && (
                                      <span className="text-green-600 font-semibold text-sm">✓ Completado</span>
                                    )}
                                  </div>
                                </div>
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>

                      {/* Info */}
                      <div className="mt-6 pt-6 border-t border-[#E3D5CA] text-sm text-[#AB9A91] flex justify-between items-center">
                        <div>
                          <p>Versión: <span className="font-semibold">v{rutina.version_asignada}</span></p>
                          <p>Asignada: <span className="font-semibold">{new Date(rutina.fecha_asignacion).toLocaleDateString()}</span></p>
                        </div>
                        <button
                          onClick={() => descargarRutinaPDF(rutina)}
                          className="bg-[#D5BDAF] hover:bg-[#AB9A91] text-white font-semibold py-2 px-4 rounded transition-colors flex items-center gap-2"
                        >
                          Descargar PDF
                        </button>
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