import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';

const GestionarRutinas = () => {
  const [rutinas, setRutinas] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [showForm, setShowForm] = useState(false);
  const [showDetalles, setShowDetalles] = useState(null);
  const [detalles, setDetalles] = useState(null);
  
  // ESTADO DEL FORMULARIO
  const [formData, setFormData] = useState({
    nombre: '',
    objetivo: '',
    descripcion: '',
    archivo: null,
    estado: 'borrador'
  });
  
  const [editingId, setEditingId] = useState(null);
  // eslint-disable-next-line no-unused-vars
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

  const handleFileChange = (e) => {
    const file = e.target.files[0];
    setFormData({ ...formData, archivo: file });
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    
    // Validación: archivo requerido SOLO para crear (no para editar)
    if (!editingId && !formData.archivo) {
      alert('⚠️ Debe cargar un archivo para crear la rutina.');
      return;
    }
    
    try {
      const token = localStorage.getItem('access_token');
      const formDataToSend = new FormData();
      formDataToSend.append('nombre', formData.nombre);
      formDataToSend.append('objetivo', formData.objetivo);
      formDataToSend.append('descripcion', formData.descripcion);
      formDataToSend.append('estado', formData.estado);
      
      // Solo agregar archivo si hay un nuevo archivo (al editar es opcional)
      if (formData.archivo) {
        formDataToSend.append('archivo', formData.archivo);
      }

      if (editingId) {
        await axios.put(`http://127.0.0.1:8000/api/gestion/rutinas/${editingId}/`, formDataToSend, {
          headers: { 
            Authorization: `Bearer ${token}`,
            'Content-Type': 'multipart/form-data'
          }
        });
        alert('✅ Rutina actualizada exitosamente');
      } else {
        const response = await axios.post('http://127.0.0.1:8000/api/gestion/rutinas/', formDataToSend, {
          headers: { 
            Authorization: `Bearer ${token}`,
            'Content-Type': 'multipart/form-data'
          }
        });
        console.log('✅ Respuesta de creación:', response.data);
        alert('✅ Rutina creada exitosamente');
      }
      
      setShowForm(false);
      resetForm();
      fetchRutinas();
    } catch (err) {
      console.error('❌ Error al guardar:', err);
      console.error('Respuesta del servidor:', err.response?.data);
      const errorMsg = err.response?.data?.archivo?.[0] || err.response?.data?.detail || 'Error al guardar la rutina. Verifica los campos.';
      alert(`❌ Error: ${errorMsg}`);
    }
  };

  const handleEdit = (rutina) => {
    setEditingId(rutina.id);
    setFormData({
      nombre: rutina.nombre,
      objetivo: rutina.objetivo || '',
      descripcion: rutina.descripcion || '',
      archivo: null, // Al editar, archivo es null (no es obligatorio cambiar)
      archivoActual: rutina.archivo, // Guardamos la URL del archivo actual
      estado: rutina.estado || 'borrador'
    });
    setShowForm(true);
  };

  const handleDelete = async (id) => {
    // 1. Confirmación inicial
    if (!window.confirm('¿Estás seguro de eliminar esta rutina?')) return;

    try {
      const token = localStorage.getItem('access_token');
      
      // 2. Llamada al Backend
      const res = await axios.delete(`http://127.0.0.1:8000/api/gestion/rutinas/${id}/`, {
        headers: { Authorization: `Bearer ${token}` }
      });

      // 3. Manejo de Respuestas Inteligentes (La lógica de tu Tesis)
      
      // CASO A: ELIMINACIÓN FÍSICA (Nadie la usaba)
      // El backend devuelve status 204 No Content
      if (res.status === 204) {
          alert("✅ Rutina eliminada permanentemente del sistema.");
      } 
      
      // CASO B: MARCADA COMO OBSOLETA (Estaba en uso)
      // El backend devuelve status 200 OK con un JSON explicativo
      else if (res.status === 200) {
          // Mostramos el mensaje detallado que armamos en Python
          // Ej: "La rutina está en uso. Se marcó como 'Obsoleta' y se notificó a los clientes."
          alert(`⚠️ AVISO DE INTEGRIDAD:\n${res.data.mensaje}`);
          
          if (res.data.notificados) {
              console.log(res.data.notificados); // Para debug
          }
      }

      // 4. Recargar la lista para ver el cambio de estado (de Publicada a Obsoleta o Desaparecida)
      fetchRutinas();

    } catch (err) {
      console.error(err);
      alert('Error al intentar eliminar la rutina. Revisa la consola.');
    }
  };

  const handleVerDetalles = async (rutinaId, rutinaNombre) => {
    try {
      const token = localStorage.getItem('access_token');
      const url = `http://127.0.0.1:8000/api/gestion/rutinas/${rutinaId}/usuarios_usando/`;
      console.log('Llamando a:', url);
      
      const response = await axios.get(url, {
        headers: { Authorization: `Bearer ${token}` }
      });
      
      console.log('Respuesta:', response.data);
      setDetalles(response.data);
      setShowDetalles(rutinaId);
    } catch (err) {
      console.error('Error al cargar detalles:', err);
      console.error('Detalles del error:', err.response?.data);
      alert('Error al cargar usuarios que usan esta rutina: ' + (err.response?.data?.detail || err.message));
    }
  };

  const resetForm = () => {
    setFormData({
      nombre: '',
      objetivo: '',
      descripcion: '',
      archivo: null,
      archivoActual: null,
      estado: 'borrador'
    });
    setEditingId(null);
  };

  // Renderizado de Badge de Estado
  const getEstadoBadge = (estado) => {
    switch (estado) {
        case 'publicada': return <span className="px-2 py-1 rounded text-xs font-bold border" style={{ backgroundColor: '#E8F5E8', color: '#2E7D2E', borderColor: '#A8D5A8' }}>PUBLICADA</span>;
        case 'borrador': return <span className="px-2 py-1 rounded text-xs font-bold border" style={{ backgroundColor: '#F5F1E8', color: '#8B7500', borderColor: '#D5BDAF' }}>BORRADOR</span>;
        case 'obsoleta': return <span className="px-2 py-1 rounded text-xs font-bold border" style={{ backgroundColor: '#FFE8E8', color: '#C73E3E', borderColor: '#F5B5B5' }}>OBSOLETA</span>;
        default: return null;
    }
  };

  return (
    <div className="min-h-screen p-6" style={{ backgroundColor: '#F5EBE0' }}>
      <div className="max-w-6xl mx-auto">
        
        {/* HEADER */}
        <div className="flex justify-between items-center mb-8">
          <div>
            <h1 className="text-3xl font-bold" style={{ color: '#817773' }}>Gestión de Rutinas</h1>
            <p style={{ color: '#8B8682' }}>Base de conocimiento experto</p>
          </div>
          {!showForm && (
            <button
              onClick={() => { resetForm(); setShowForm(true); }}
              className="text-white px-6 py-3 rounded-lg font-bold shadow-lg transition-transform transform hover:-translate-y-1"
              style={{ backgroundColor: '#AB9A91' }}
              onMouseEnter={(e) => e.target.style.backgroundColor = '#817773'}
              onMouseLeave={(e) => e.target.style.backgroundColor = '#AB9A91'}
            >
              + Nueva Rutina
            </button>
          )}
        </div>

        {error && (
          <div className="mb-6 p-4 rounded shadow-sm border-l-4" style={{ backgroundColor: '#FFE8E8', borderColor: '#C73E3E', color: '#C73E3E' }}>
            {error}
          </div>
        )}

        {/* --- FORMULARIO DE CREACIÓN/EDICIÓN --- */}
        {showForm ? (
          <div className="rounded-xl shadow-xl p-8 border" style={{ backgroundColor: 'white', borderColor: '#D5D1CC' }}>
            <h2 className="text-2xl font-bold mb-6" style={{ color: '#817773', borderBottom: '2px solid #E3D5CA', paddingBottom: '0.5rem' }}>
              {editingId ? '✏️ Editar Rutina' : 'Nueva Rutina'}
            </h2>
            
            <form onSubmit={handleSubmit} className="space-y-6">
              
              {/* FILA 1: Nombre y Estado */}
              <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                <div className="md:col-span-2">
                  <label className="block text-sm font-bold mb-1" style={{ color: '#817773' }}>Nombre de la Rutina</label>
                  <input
                    type="text" name="nombre"
                    value={formData.nombre} onChange={handleInputChange}
                    className="w-full border p-2 rounded focus:ring-2 outline-none"
                    style={{ borderColor: '#D5D1CC', '--tw-ring-color': '#AB9A91' }}
                    placeholder="Ej: Rutina Detox & Equilibrio" required
                  />
                </div>
                <div>
                  <label className="block text-sm font-bold mb-1" style={{ color: '#817773' }}>Estado</label>
                  <select
                    name="estado"
                    value={formData.estado} onChange={handleInputChange}
                    className="w-full border p-2 rounded font-medium"
                    style={{ borderColor: '#D5D1CC', backgroundColor: '#F5EBE0' }}
                  >
                    <option value="borrador">Borrador</option>
                    <option value="publicada">Publicada</option>
                    <option value="obsoleta">Obsoleta</option>
                  </select>
                </div>
              </div>

              {/* FILA 2: Objetivo */}
              <div>
                <label className="block text-sm font-bold mb-1" style={{ color: '#817773' }}>Objetivo (Para el diagnóstico)</label>
                <input
                  type="text" name="objetivo"
                  value={formData.objetivo} onChange={handleInputChange}
                  className="w-full border p-2 rounded focus:ring-2 outline-none"
                  style={{ borderColor: '#D5D1CC', '--tw-ring-color': '#AB9A91' }}
                  placeholder="Ej: Regular oleosidad sin resecar puntas" required
                />
              </div>

              {/* Descripción (Notas internas) */}
              <div>
                <label className="block text-sm font-bold mb-1" style={{ color: '#817773' }}>Notas Internas (Opcional)</label>
                <textarea
                  name="descripcion"
                  value={formData.descripcion}
                  onChange={handleInputChange}
                  className="w-full border p-2 rounded focus:ring-2 outline-none"
                  style={{ borderColor: '#D5D1CC', '--tw-ring-color': '#AB9A91' }}
                  rows="3"
                  placeholder="Notas internas sobre la rutina (no visible para cliente)..."
                />
              </div>

              {/* CARGA DE ARCHIVO PDF */}
              <div>
                <label className="block text-sm font-bold mb-1" style={{ color: '#817773' }}>
                  📄 Cargar Rutina (PDF/Imagen)
                </label>
                <p className="text-xs mb-3" style={{ color: '#8B8682' }}>
                  Sube el diseño de la rutina en formato PDF, JPG o PNG. (Máx. 10MB)
                </p>
                
                {/* Mostrar archivo actual si está editando */}
                {editingId && formData.archivoActual && (
                  <div className="mb-4 p-3 rounded-lg border" style={{ backgroundColor: '#E8F0F5', borderColor: '#AB9A91' }}>
                    <p className="text-sm font-bold mb-2" style={{ color: '#817773' }}>📎 Archivo actual:</p>
                    <a 
                      href={formData.archivoActual} 
                      target="_blank" 
                      rel="noopener noreferrer"
                      className="underline text-sm"
                      style={{ color: '#AB9A91' }}
                    >
                      Ver archivo guardado
                    </a>
                    <p className="text-xs mt-2" style={{ color: '#817773' }}>Carga un nuevo archivo para reemplazarlo (opcional)</p>
                  </div>
                )}
                
                <input
                  type="file"
                  name="archivo"
                  accept=".pdf,.jpg,.jpeg,.png"
                  onChange={handleFileChange}
                  className="w-full border-2 border-dashed p-4 rounded-lg text-gray-700 cursor-pointer transition"
                  style={{ borderColor: '#D5BDAF' }}
                  required={!editingId}
                />
                {formData.archivo && (
                  <p className="text-xs mt-2" style={{ color: '#5A9B6F' }}>✓ {formData.archivo.name}</p>
                )}
              </div>

              {/* BOTONES ACCIÓN */}
              <div className="flex justify-end gap-3 pt-4">
                <button
                  type="button"
                  onClick={() => { setShowForm(false); resetForm(); }}
                  className="px-6 py-2 rounded font-bold transition"
                  style={{ backgroundColor: '#E3D5CA', color: '#817773' }}
                  onMouseEnter={(e) => e.target.style.backgroundColor = '#D5BDAF'}
                  onMouseLeave={(e) => e.target.style.backgroundColor = '#E3D5CA'}
                >
                  Cancelar
                </button>
                <button
                  type="submit"
                  className="px-6 py-2 text-white rounded font-bold shadow-lg transition"
                  style={{ backgroundColor: '#817773' }}
                  onMouseEnter={(e) => e.target.style.backgroundColor = '#5A5451'}
                  onMouseLeave={(e) => e.target.style.backgroundColor = '#817773'}
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
                <div className="text-center py-12 rounded-xl shadow" style={{ backgroundColor: 'white' }}>
                    <p style={{ color: '#8B8682' }} className="text-lg">No hay rutinas creadas.</p>
                    <p style={{ color: '#ABA89E' }} className="text-sm">Crea una para comenzar a recomendarla.</p>
                </div>
            )}

            {rutinas.map((rutina) => (
              <div key={rutina.id} className="rounded-xl shadow-md overflow-hidden border-l-4 hover:shadow-lg transition-shadow" style={{ backgroundColor: 'white', borderColor: '#D5BDAF' }}>
                <div className="p-6 flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
                  <div className="flex-1">
                    <div className="flex items-center gap-3 mb-1">
                        <h3 className="text-xl font-bold" style={{ color: '#817773' }}>{rutina.nombre}</h3>
                        {getEstadoBadge(rutina.estado)}
                        <span className="text-xs rounded border px-2 py-0.5" style={{ backgroundColor: '#E3D5CA', color: '#817773', borderColor: '#D5BDAF' }}>
                            v{rutina.version || 1}
                        </span>
                    </div>
                    <p className="text-sm font-medium italic mb-2" style={{ color: '#8B8682' }}>{rutina.objetivo}</p>
                    <p className="text-sm line-clamp-2" style={{ color: '#5A5451' }}>{rutina.descripcion}</p>
                    
                    <div className="mt-3 flex items-center gap-4 text-xs" style={{ color: '#ABA89E' }}>
                        {rutina.archivo && <span>📄 Con archivo adjunto</span>}
                        <span> Creada por: {rutina.creada_por_nombre || 'Sistema'}</span>
                        <span className="rounded font-bold px-2 py-0.5" style={{ backgroundColor: '#E8D5CA', color: '#817773' }}>
                          👥 {rutina.usuarios_usando || 0} usuario{rutina.usuarios_usando !== 1 ? 's' : ''}
                        </span>
                    </div>
                  </div>

                  <div className="flex gap-2">
                    {rutina.usuarios_usando > 0 && (
                      <button
                        onClick={() => handleVerDetalles(rutina.id, rutina.nombre)}
                        className="px-4 py-2 rounded font-bold transition"
                        style={{ backgroundColor: '#E8D5CA', color: '#817773' }}
                        onMouseEnter={(e) => e.target.style.backgroundColor = '#D5BDAF'}
                        onMouseLeave={(e) => e.target.style.backgroundColor = '#E8D5CA'}
                      >
                        Ver Usuarios
                      </button>
                    )}
                    <button
                      onClick={() => handleEdit(rutina)}
                      className="px-4 py-2 rounded font-bold transition"
                      style={{ backgroundColor: '#E3D5CA', color: '#817773' }}
                      onMouseEnter={(e) => e.target.style.backgroundColor = '#D5BDAF'}
                      onMouseLeave={(e) => e.target.style.backgroundColor = '#E3D5CA'}
                    >
                      Editar
                    </button>
                    <button
                      onClick={() => handleDelete(rutina.id)}
                      className="px-4 py-2 rounded font-bold transition text-white"
                      style={{ backgroundColor: '#AB9A91' }}
                      onMouseEnter={(e) => e.target.style.backgroundColor = '#817773'}
                      onMouseLeave={(e) => e.target.style.backgroundColor = '#AB9A91'}
                    >
                      Eliminar
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* MODAL DE DETALLES DE USUARIOS */}
        {showDetalles && detalles && (
          <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
            <div className="bg-white rounded-xl shadow-2xl max-w-2xl w-full max-h-[80vh] overflow-y-auto">
              <div className="sticky top-0 text-white p-6 flex justify-between items-center" style={{ background: 'linear-gradient(135deg, #AB9A91 0%, #817773 100%)' }}>
                <div>
                  <h2 className="text-2xl font-bold">{detalles.rutina_nombre}</h2>
                  <p className="mt-1" style={{ color: '#E3D5CA' }}>👥 {detalles.total_usuarios} usuario{detalles.total_usuarios !== 1 ? 's' : ''} utilizando</p>
                </div>
                <button
                  onClick={() => setShowDetalles(null)}
                  className="font-bold px-4 py-2 rounded"
                  style={{ backgroundColor: 'rgba(255,255,255,0.1)' }}
                  onMouseEnter={(e) => e.target.style.backgroundColor = 'rgba(255,255,255,0.2)'}
                  onMouseLeave={(e) => e.target.style.backgroundColor = 'rgba(255,255,255,0.1)'}
                >
                  ✕ Cerrar
                </button>
              </div>

              <div className="p-6">
                {detalles.usuarios.length === 0 ? (
                  <p style={{ color: '#8B8682' }} className="text-center py-8">No hay usuarios usando esta rutina</p>
                ) : (
                  <div className="space-y-4">
                    {detalles.usuarios.map((usuario, idx) => (
                      <div key={idx} className="border rounded-lg p-4 hover:bg-opacity-100 transition" style={{ backgroundColor: '#F5EBE0', borderColor: '#D5D1CC' }}>
                        <div className="flex justify-between items-start">
                          <div>
                            <h3 className="font-bold" style={{ color: '#817773' }}>{usuario.nombre}</h3>
                            <p className="text-sm" style={{ color: '#8B8682' }}>{usuario.email}</p>
                            <p className="text-xs mt-2" style={{ color: '#ABA89E' }}>
                              Asignada: {new Date(usuario.fecha_asignacion).toLocaleDateString('es-ES')}
                            </p>
                          </div>
                          <div className="text-right">
                            <span className="inline-block px-3 py-1 rounded font-bold text-xs mb-2" style={{ backgroundColor: '#E3D5CA', color: '#817773' }}>
                              v{usuario.version_asignada}
                            </span>
                            <p className="text-xs" style={{ color: '#8B8682' }}>
                              {usuario.estado === 'activa' && <span style={{ color: '#2E7D2E' }}>✓ Activa</span>}
                              {usuario.estado === 'inactiva' && <span style={{ color: '#8B8682' }}>○ Inactiva</span>}
                            </p>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default GestionarRutinas;