import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';

const GestionarRutinas = () => {
  const [rutinas, setRutinas] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [showForm, setShowForm] = useState(false);
  
  // ESTADO DEL FORMULARIO (Actualizado con campos del Diagrama)
  const [formData, setFormData] = useState({
    nombre: '',
    objetivo: '',
    descripcion: '',
    estado: 'borrador', // Valor por defecto
    pasos: [{ orden: 1, titulo: '', descripcion: '', frecuencia: '' }]
  });
  
  const [editingId, setEditingId] = useState(null);
  const navigate = useNavigate();

  useEffect(() => {
    fetchRutinas();
  }, []);

  const fetchRutinas = async () => {
    try {
      setLoading(true);
      const token = localStorage.getItem('access_token');
      // Asegúrate que el puerto sea el correcto (8000)
      const response = await axios.get('http://127.0.0.1:8000/api/gestion/rutinas/', {
        headers: { Authorization: `Bearer ${token}` }
      });
      
      const data = Array.isArray(response.data) ? response.data : response.data.results || [];
      setRutinas(data);
      setError('');
    } catch (err) {
      console.error(err);
      setError('Error al cargar rutinas.');
    } finally {
      setLoading(false);
    }
  };

  const handleInputChange = (e) => {
    const { name, value } = e.target;
    setFormData({ ...formData, [name]: value });
  };

  // Manejo de Pasos Dinámicos
  const handlePasoChange = (index, field, value) => {
    const nuevosPasos = [...formData.pasos];
    nuevosPasos[index][field] = value;
    setFormData({ ...formData, pasos: nuevosPasos });
  };

  const addPaso = () => {
    setFormData({
      ...formData,
      pasos: [...formData.pasos, { orden: formData.pasos.length + 1, titulo: '', descripcion: '', frecuencia: '' }]
    });
  };

  const removePaso = (index) => {
    const nuevosPasos = formData.pasos.filter((_, i) => i !== index);
    // Reordenar
    const pasosReordenados = nuevosPasos.map((p, i) => ({ ...p, orden: i + 1 }));
    setFormData({ ...formData, pasos: pasosReordenados });
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    try {
      const token = localStorage.getItem('access_token');
      const payload = { ...formData }; // Enviamos el estado ('borrador'/'publicada')

      if (editingId) {
        await axios.put(`http://127.0.0.1:8000/api/gestion/rutinas/${editingId}/`, payload, {
          headers: { Authorization: `Bearer ${token}` }
        });
        alert('Rutina actualizada exitosamente');
      } else {
        await axios.post('http://127.0.0.1:8000/api/gestion/rutinas/', payload, {
          headers: { Authorization: `Bearer ${token}` }
        });
        alert('Rutina creada exitosamente');
      }
      
      setShowForm(false);
      resetForm();
      fetchRutinas();
    } catch (err) {
      console.error(err);
      setError('Error al guardar la rutina. Verifica los campos.');
    }
  };

  const handleEdit = (rutina) => {
    setEditingId(rutina.id);
    // Aseguramos que los pasos tengan frecuencia (para evitar errores si es null)
    const pasosSeguros = rutina.pasos.map(p => ({
        ...p,
        frecuencia: p.frecuencia || ''
    }));
    
    setFormData({
      nombre: rutina.nombre,
      objetivo: rutina.objetivo || '',
      descripcion: rutina.descripcion,
      estado: rutina.estado || 'borrador', 
      pasos: pasosSeguros
    });
    setShowForm(true);
  };

  const handleDelete = async (id) => {
    if (window.confirm('¿Estás seguro de eliminar esta rutina?')) {
      try {
        const token = localStorage.getItem('access_token');
        await axios.delete(`http://127.0.0.1:8000/api/gestion/rutinas/${id}/`, {
          headers: { Authorization: `Bearer ${token}` }
        });
        fetchRutinas();
      } catch (err) {
        setError('Error al eliminar la rutina');
      }
    }
  };

  const resetForm = () => {
    setFormData({
      nombre: '',
      objetivo: '',
      descripcion: '',
      estado: 'borrador',
      pasos: [{ orden: 1, titulo: '', descripcion: '', frecuencia: '' }]
    });
    setEditingId(null);
  };

  // Renderizado de Badge de Estado
  const getEstadoBadge = (estado) => {
    switch (estado) {
        case 'publicada': return <span className="bg-green-100 text-green-800 px-2 py-1 rounded text-xs font-bold border border-green-200">PUBLICADA</span>;
        case 'borrador': return <span className="bg-yellow-100 text-yellow-800 px-2 py-1 rounded text-xs font-bold border border-yellow-200">BORRADOR</span>;
        case 'obsoleta': return <span className="bg-red-100 text-red-800 px-2 py-1 rounded text-xs font-bold border border-red-200">OBSOLETA</span>;
        default: return null;
    }
  };

  return (
    <div className="min-h-screen bg-gray-50 p-6">
      <div className="max-w-6xl mx-auto">
        
        {/* HEADER */}
        <div className="flex justify-between items-center mb-8">
          <div>
            <h1 className="text-3xl font-bold text-gray-800">Gestión de Rutinas</h1>
            <p className="text-gray-500">Base de conocimiento experto</p>
          </div>
          {!showForm && (
            <button
              onClick={() => { resetForm(); setShowForm(true); }}
              className="bg-pink-600 hover:bg-pink-700 text-white px-6 py-3 rounded-lg font-bold shadow-lg transition-transform transform hover:-translate-y-1"
            >
              + Nueva Rutina
            </button>
          )}
        </div>

        {error && (
          <div className="bg-red-100 border-l-4 border-red-500 text-red-700 p-4 mb-6 rounded shadow-sm">
            {error}
          </div>
        )}

        {/* --- FORMULARIO DE CREACIÓN/EDICIÓN --- */}
        {showForm ? (
          <div className="bg-white rounded-xl shadow-xl p-8 border border-gray-200 animate-fade-in-down">
            <h2 className="text-2xl font-bold text-gray-800 mb-6 border-b pb-2">
              {editingId ? '✏️ Editar Rutina' : 'Nueva Rutina'}
            </h2>
            
            <form onSubmit={handleSubmit} className="space-y-6">
              
              {/* FILA 1: Nombre y Estado */}
              <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                <div className="md:col-span-2">
                  <label className="block text-sm font-bold text-gray-700 mb-1">Nombre de la Rutina</label>
                  <input
                    type="text" name="nombre"
                    value={formData.nombre} onChange={handleInputChange}
                    className="w-full border p-2 rounded focus:ring-2 focus:ring-pink-500 outline-none"
                    placeholder="Ej: Rutina Detox & Equilibrio" required
                  />
                </div>
                <div>
                  <label className="block text-sm font-bold text-gray-700 mb-1">Estado</label>
                  <select
                    name="estado"
                    value={formData.estado} onChange={handleInputChange}
                    className="w-full border p-2 rounded bg-gray-50 font-medium"
                  >
                    <option value="borrador">Borrador</option>
                    <option value="publicada">Publicada</option>
                    <option value="obsoleta">Obsoleta</option>
                  </select>
                </div>
              </div>

              {/* FILA 2: Objetivo */}
              <div>
                <label className="block text-sm font-bold text-gray-700 mb-1">Objetivo (Para el diagnóstico)</label>
                <input
                  type="text" name="objetivo"
                  value={formData.objetivo} onChange={handleInputChange}
                  className="w-full border p-2 rounded focus:ring-2 focus:ring-pink-500 outline-none"
                  placeholder="Ej: Regular oleosidad sin resecar puntas" required
                />
              </div>

              {/* Descripción */}
              <div>
                <label className="block text-sm font-bold text-gray-700 mb-1">Descripción General</label>
                <textarea
                  name="descripcion"
                  value={formData.descripcion} onChange={handleInputChange}
                  className="w-full border p-2 rounded focus:ring-2 focus:ring-pink-500 outline-none"
                  rows="2" required
                />
              </div>

              {/* SECCIÓN PASOS */}
              <div className="bg-gray-50 p-6 rounded-lg border border-gray-200">
                <h3 className="text-lg font-bold text-pink-600 mb-4">Pasos de la Rutina</h3>
                
                {formData.pasos.map((paso, index) => (
                  <div key={index} className="mb-4 bg-white p-4 rounded shadow-sm border border-gray-200 relative">
                    <span className="absolute top-2 right-2 text-xs font-bold text-gray-300">PASO {index + 1}</span>
                    
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                        <div className="md:col-span-2">
                            <input
                                type="text"
                                placeholder="Título (Ej: Lavado con Shampoo Neutro)"
                                value={paso.titulo}
                                onChange={(e) => handlePasoChange(index, 'titulo', e.target.value)}
                                className="w-full border p-2 rounded font-bold" required
                            />
                        </div>
                        <div className="md:col-span-2">
                            <input
                                type="text"
                                placeholder="Frecuencia (Ej: Cada 48hs)"
                                value={paso.frecuencia}
                                onChange={(e) => handlePasoChange(index, 'frecuencia', e.target.value)}
                                className="w-full border p-2 rounded text-sm bg-blue-50" required
                            />
                        </div>
                        <div className="md:col-span-2">
                            <textarea
                                placeholder="Instrucciones detalladas..."
                                value={paso.descripcion}
                                onChange={(e) => handlePasoChange(index, 'descripcion', e.target.value)}
                                className="w-full border p-2 rounded text-sm" rows="2" required
                            />
                        </div>
                    </div>
                    
                    {formData.pasos.length > 1 && (
                      <button
                        type="button"
                        onClick={() => removePaso(index)}
                        className="text-red-500 text-xs font-bold mt-2 hover:underline"
                      >
                         Eliminar Paso
                      </button>
                    )}
                  </div>
                ))}
                
                <button
                  type="button"
                  onClick={addPaso}
                  className="w-full py-2 border-2 border-dashed border-pink-300 text-pink-600 font-bold rounded hover:bg-pink-50 transition"
                >
                  + Agregar Otro Paso
                </button>
              </div>

              {/* BOTONES ACCIÓN */}
              <div className="flex justify-end gap-3 pt-4">
                <button
                  type="button"
                  onClick={() => { setShowForm(false); resetForm(); }}
                  className="px-6 py-2 bg-gray-300 text-gray-700 rounded font-bold hover:bg-gray-400"
                >
                  Cancelar
                </button>
                <button
                  type="submit"
                  className="px-6 py-2 bg-gray-900 text-white rounded font-bold hover:bg-gray-800 shadow-lg"
                >
                  Guardar Rutina
                </button>
              </div>
            </form>
          </div>
        ) : (
          
          /* --- LISTA DE RUTINAS --- */
          <div className="grid grid-cols-1 gap-6">
            {rutinas.length === 0 && !loading && (
                <div className="text-center py-12 bg-white rounded-xl shadow">
                    <p className="text-gray-400 text-lg">No hay rutinas creadas.</p>
                    <p className="text-gray-500 text-sm">Crea una para comenzar a recomendarla.</p>
                </div>
            )}

            {rutinas.map((rutina) => (
              <div key={rutina.id} className="bg-white rounded-xl shadow-md overflow-hidden border-l-4 border-pink-500 hover:shadow-lg transition-shadow">
                <div className="p-6 flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
                  <div className="flex-1">
                    <div className="flex items-center gap-3 mb-1">
                        <h3 className="text-xl font-bold text-gray-800">{rutina.nombre}</h3>
                        {getEstadoBadge(rutina.estado)}
                        <span className="text-xs bg-blue-50 text-blue-600 px-2 py-0.5 rounded border border-blue-100">
                            v{rutina.version || 1}
                        </span>
                    </div>
                    <p className="text-sm text-gray-500 font-medium italic mb-2">{rutina.objetivo}</p>
                    <p className="text-gray-600 text-sm line-clamp-2">{rutina.descripcion}</p>
                    
                    <div className="mt-3 flex items-center gap-4 text-xs text-gray-400">
                        <span> {rutina.pasos?.length || 0} pasos</span>
                        <span> Creada por: {rutina.creador_nombre || 'Sistema'}</span>
                    </div>
                  </div>

                  <div className="flex gap-2">
                    <button
                      onClick={() => handleEdit(rutina)}
                      className="px-4 py-2 bg-blue-50 text-blue-600 rounded font-bold hover:bg-blue-100 transition"
                    >
                      Editar
                    </button>
                    <button
                      onClick={() => handleDelete(rutina.id)}
                      className="px-4 py-2 bg-red-50 text-red-600 rounded font-bold hover:bg-red-100 transition"
                    >
                      Eliminar
                    </button>
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

export default GestionarRutinas;