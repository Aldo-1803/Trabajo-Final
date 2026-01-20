import React, { useState, useEffect } from 'react';
import axios from 'axios';
import fichasTecnicasApi from '../../api/fichasTecnicasApi';
import { confirmarAccion, notify } from '../../utils/notificaciones';

const VisualizadorFichas = () => {
  const [fichas, setFichas] = useState([]);
  const [filtro, setFiltro] = useState('todas');
  const [cargando, setCargando] = useState(false);
  const [error, setError] = useState('');
  const [fichaSeleccionada, setFichaSeleccionada] = useState(null);

  useEffect(() => {
    cargarFichas();
  }, [filtro]);

  const cargarFichas = async () => {
    setCargando(true);
    setError('');
    try {
      let datos;
      if (filtro === 'mias') {
        datos = await fichasTecnicasApi.obtenerMisFichas();
      } else {
        datos = await fichasTecnicasApi.obtenerTodas();
      }
      setFichas(Array.isArray(datos) ? datos : [datos]);
    } catch (err) {
      console.error('Error cargando fichas:', err);
      setError('Error al cargar las fichas técnicas');
    } finally {
      setCargando(false);
    }
  };

  const handleEliminar = async (id) => {
    const result = await confirmarAccion({
      title: "¿Eliminar ficha?",
      text: "Esta acción no se puede deshacer",
      confirmButtonText: "Sí, eliminar"
    });
    if (!result.isConfirmed) return;

    try {
      await fichasTecnicasApi.eliminar(id);
      setFichas(fichas.filter(f => f.id !== id));
      setFichaSeleccionada(null);
      notify.success('Ficha eliminada correctamente');
    } catch (err) {
      notify.error('Error al eliminar la ficha');
      console.error(err);
    }
  };

  return (
    <div className="max-w-7xl mx-auto my-5 p-5 bg-white rounded-lg shadow-md">
      <div className="flex justify-between items-center mb-7 pb-5 border-b-4 border-blue-500">
        <h2 className="text-2xl font-bold text-gray-800 m-0">📊 Fichas Técnicas Registradas</h2>
        <div className="flex gap-2.5">
          <button
            className={`px-4 py-2 border-2 rounded-md font-medium transition-all ${
              filtro === 'todas'
                ? 'bg-blue-500 text-white border-blue-500'
                : 'bg-white text-gray-700 border-gray-300 hover:border-blue-500 hover:text-blue-500'
            }`}
            onClick={() => setFiltro('todas')}
          >
            Todas
          </button>
          <button
            className={`px-4 py-2 border-2 rounded-md font-medium transition-all ${
              filtro === 'mias'
                ? 'bg-blue-500 text-white border-blue-500'
                : 'bg-white text-gray-700 border-gray-300 hover:border-blue-500 hover:text-blue-500'
            }`}
            onClick={() => setFiltro('mias')}
          >
            Mis Fichas
          </button>
        </div>
      </div>

      {error && <div className="bg-red-100 text-red-800 p-4 rounded-md mb-5 border-l-4 border-red-800">{error}</div>}

      {cargando ? (
        <div className="text-center py-10 text-gray-500 text-base">Cargando fichas...</div>
      ) : fichas.length === 0 ? (
        <div className="text-center py-10 text-gray-500 text-base">No hay fichas técnicas registradas</div>
      ) : (
        <div className="grid grid-cols-[350px_1fr] gap-7">
          <div className="flex flex-col gap-2.5 max-h-96 overflow-y-auto pr-2.5">
            {fichas.map(ficha => (
              <div
                key={ficha.id}
                className={`p-4 border-2 rounded-lg cursor-pointer transition-all ${
                  fichaSeleccionada?.id === ficha.id
                    ? 'border-blue-500 bg-blue-50'
                    : 'border-gray-200 bg-gray-50 hover:border-blue-500 hover:bg-blue-50'
                }`}
                onClick={() => setFichaSeleccionada(ficha)}
              >
                <div className="flex justify-between items-start mb-2.5">
                  <h3 className="text-gray-800 m-0 text-sm flex-1">{ficha.servicio_nombre}</h3>
                  <span className="text-xs text-gray-500 whitespace-nowrap ml-2.5">{new Date(ficha.fecha_registro).toLocaleDateString('es-AR')}</span>
                </div>
                <div className="text-xs text-gray-600">
                  <p className="overflow-hidden text-ellipsis whitespace-nowrap m-1.25"><strong>Profesional:</strong> {ficha.profesional_nombre}</p>
                  <p className="overflow-hidden text-ellipsis whitespace-nowrap m-1.25"><strong>Fórmula:</strong> {ficha.formula.substring(0, 60)}...</p>
                </div>
              </div>
            ))}
          </div>

          {fichaSeleccionada && (
            <div className="bg-white border-2 border-blue-500 rounded-lg overflow-hidden flex flex-col max-h-96 overflow-y-auto">
              <div className="flex justify-between items-center p-5 bg-gray-100 border-b border-gray-300 sticky top-0 z-10">
                <h3 className="text-gray-800 m-0 text-lg">{fichaSeleccionada.servicio_nombre}</h3>
                <button className="bg-none border-none text-2xl cursor-pointer text-gray-500 transition-colors hover:text-gray-800" onClick={() => setFichaSeleccionada(null)}>✕</button>
              </div>

              <div className="p-5">
                
                {/* Información General */}
                <section className="mb-6 pb-5 border-b border-gray-200 last:mb-0 last:pb-0 last:border-b-0">
                  <h4 className="text-blue-500 m-0 mb-3 text-sm font-semibold uppercase tracking-wide">Información General</h4>
                  <div className="grid grid-cols-2 gap-4">
                    <div className="flex flex-col">
                      <label className="font-semibold text-gray-600 text-xs mb-1">Profesional</label>
                      <p className="text-gray-800 m-0 text-sm">{fichaSeleccionada.profesional_nombre}</p>
                    </div>
                    <div className="flex flex-col">
                      <label className="font-semibold text-gray-600 text-xs mb-1">Fecha Registro</label>
                      <p className="text-gray-800 m-0 text-sm">{new Date(fichaSeleccionada.fecha_registro).toLocaleString('es-AR')}</p>
                    </div>
                  </div>
                </section>

                {/* Plantilla Base */}
                {fichaSeleccionada.formula_base_servicio && (
                  <section className="mb-6 pb-5 border-b border-gray-200 last:mb-0 last:pb-0 last:border-b-0">
                    <h4 className="text-blue-500 m-0 mb-3 text-sm font-semibold uppercase tracking-wide">Estructura Base</h4>
                    <div className="bg-blue-50 p-3 rounded-md border-l-4 border-blue-500 text-blue-700 text-sm font-mono">
                      {fichaSeleccionada.formula_base_servicio}
                    </div>
                  </section>
                )}

                {/* Fórmula Utilizada */}
                <section className="mb-6 pb-5 border-b border-gray-200 last:mb-0 last:pb-0 last:border-b-0">
                  <h4 className="text-blue-500 m-0 mb-3 text-sm font-semibold uppercase tracking-wide">Fórmula Utilizada</h4>
                  <div className="bg-gray-100 p-3 rounded-md border-l-4 border-blue-500 text-gray-800 text-sm leading-relaxed whitespace-pre-wrap">
                    {fichaSeleccionada.formula}
                  </div>
                </section>

                {/* Observaciones Proceso */}
                {fichaSeleccionada.observaciones_proceso && (
                  <section className="mb-6 pb-5 border-b border-gray-200 last:mb-0 last:pb-0 last:border-b-0">
                    <h4 className="text-blue-500 m-0 mb-3 text-sm font-semibold uppercase tracking-wide">Observaciones del Proceso</h4>
                    <div className="bg-gray-100 p-3 rounded-md border-l-4 border-blue-500 text-gray-800 text-sm leading-relaxed whitespace-pre-wrap">
                      {fichaSeleccionada.observaciones_proceso}
                    </div>
                  </section>
                )}

                {/* Estado Final del Cabello */}
                <section className="mb-6 pb-5 border-b border-gray-200 last:mb-0 last:pb-0 last:border-b-0">
                  <h4 className="text-blue-500 m-0 mb-3 text-sm font-semibold uppercase tracking-wide">Estado Post-Servicio</h4>
                  <div className="grid grid-cols-2 gap-4">
                    <div className="flex flex-col">
                      <label className="font-semibold text-gray-600 text-xs mb-1">Porosidad</label>
                      <p className="text-gray-800 m-0 text-sm">{fichaSeleccionada.porosidad_final_nombre || 'No registrada'}</p>
                    </div>
                    <div className="flex flex-col">
                      <label className="font-semibold text-gray-600 text-xs mb-1">Estado General</label>
                      <p className="text-gray-800 m-0 text-sm">{fichaSeleccionada.estado_general_final_nombre || 'No registrado'}</p>
                    </div>
                  </div>
                </section>

                {/* Resultado */}
                {fichaSeleccionada.resultado_post_servicio && (
                  <section className="mb-6 pb-5 border-b border-gray-200 last:mb-0 last:pb-0 last:border-b-0">
                    <h4 className="text-blue-500 m-0 mb-3 text-sm font-semibold uppercase tracking-wide">Resultado Final</h4>
                    <div className="bg-gray-100 p-3 rounded-md border-l-4 border-blue-500 text-gray-800 text-sm leading-relaxed whitespace-pre-wrap">
                      {fichaSeleccionada.resultado_post_servicio}
                    </div>
                  </section>
                )}

                {/* Foto */}
                {fichaSeleccionada.foto_resultado && (
                  <section className="mb-6 pb-5 border-b border-gray-200 last:mb-0 last:pb-0 last:border-b-0">
                    <h4 className="text-blue-500 m-0 mb-3 text-sm font-semibold uppercase tracking-wide">Foto del Resultado</h4>
                    <img
                      src={fichaSeleccionada.foto_resultado}
                      alt="Resultado"
                      className="w-full h-auto rounded-md border-2 border-blue-500"
                    />
                  </section>
                )}

                {/* Acciones */}
                <div className="flex gap-2.5 mt-5 pt-5 border-t border-gray-200">
                  <button
                    className="px-4 py-2.5 bg-red-600 text-white border-none rounded-md cursor-pointer font-medium transition-all hover:bg-red-500 hover:translate-y-px"
                    onClick={() => handleEliminar(fichaSeleccionada.id)}
                  >
                    🗑️ Eliminar
                  </button>
                </div>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default VisualizadorFichas;
