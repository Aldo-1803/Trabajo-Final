import React, { useState, useEffect } from 'react';
import axios from 'axios';

const MiAgenda = () => {
  const [agenda, setAgenda] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    const fetchAgenda = async () => {
      try {
        const token = localStorage.getItem('access_token');
        if (!token) {
          setError('No estás autenticado. Por favor inicia sesión.');
          setLoading(false);
          return;
        }

        const config = {
          headers: {
            'Authorization': `Bearer ${token}`
          }
        };
        
        const response = await axios.get('http://127.0.0.1:8000/api/gestion/mi-agenda/', config);
        
        // Manejar diferentes formatos de respuesta
        let agendaData = Array.isArray(response.data) ? response.data : response.data.results || [];
        
        setAgenda(agendaData);
        setLoading(false);
      } catch (err) {
        console.error('Error completo:', err);
        setError('Error al cargar tu agenda de cuidados. ' + (err.response?.data?.detail || err.message));
        setLoading(false);
      }
    };

    fetchAgenda();
  }, []);

  if (loading) return (
    <div className="min-h-screen flex items-center justify-center" style={{ background: 'linear-gradient(135deg, #e8c39e 0%, #ffffff 100%)' }}>
      <div className="text-center">
        <div className="animate-spin rounded-full h-16 w-16 border-4 border-gray-300 border-t-rose-500 mx-auto mb-4"></div>
        <p className="text-gray-700">Cargando tu rutina personalizada...</p>
      </div>
    </div>
  );

  return (
    <div className="min-h-screen" style={{ background: 'linear-gradient(135deg, #e8c39e 0%, #ffffff 100%)' }}>
      {/* Header */}
      <div className="px-6 sm:px-8 py-12 text-white" style={{ background: 'linear-gradient(135deg, #7a5c3c 0%, #b08e6b 100%)' }}>
        <div className="max-w-4xl mx-auto">
          <h1 className="text-4xl font-bold mb-2">📋 Mi Agenda Capilar</h1>
          <p className="text-amber-50">Tu rutina personalizada de cuidados</p>
        </div>
      </div>

      {/* Contenido */}
      <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
        {error && (
          <div className="mb-6 p-4 rounded-lg border-l-4" style={{ backgroundColor: '#ffe8e8', borderColor: '#c73e3e' }}>
            <p style={{ color: '#c73e3e' }} className="font-medium">⚠️ {error}</p>
          </div>
        )}
        
        {agenda.length === 0 ? (
          <div className="bg-white rounded-2xl p-12 shadow-lg text-center">
            <p className="text-2xl text-gray-600 mb-4">📝 Sin tareas pendientes</p>
            <p className="text-gray-500">No tienes tareas de cuidados asignadas. ¡Agenda un turno para recibir tu rutina personalizada!</p>
          </div>
        ) : (
          <div className="space-y-4">
            {agenda.map((item) => (
              <div 
                key={item.id} 
                className={`p-6 border-l-4 rounded-lg shadow-md ${
                  item.tipo === 'RESTRICCION' 
                    ? 'bg-red-50 border-red-500' 
                    : 'bg-green-50 border-green-500'
                }`}
              >
                <div className="flex justify-between items-start mb-3">
                  <h3 className="font-bold text-xl text-gray-800">{item.titulo}</h3>
                  <span className="text-sm text-gray-600 font-semibold bg-white px-3 py-1 rounded">
                    📅 {item.fecha}
                  </span>
                </div>
                <p className="text-gray-700 mb-3">{item.descripcion}</p>
                <span className={`text-xs uppercase tracking-wide font-semibold px-3 py-1 rounded-full ${
                  item.tipo === 'RESTRICCION'
                    ? 'bg-red-200 text-red-700'
                    : 'bg-green-200 text-green-700'
                }`}>
                  {item.tipo}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

export default MiAgenda;