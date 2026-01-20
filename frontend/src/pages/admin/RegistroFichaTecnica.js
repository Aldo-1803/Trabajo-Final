import React, { useState, useEffect } from 'react';
import axios from 'axios';
import fichasTecnicasApi from '../../api/fichasTecnicasApi';

const RegistroFichaTecnica = ({ turnoId, onExito, onCancelar }) => {
  const [formulario, setFormulario] = useState({
    detalle_turno: null,
    formula: '',
    observaciones_proceso: '',
    porosidad_final: null,
    estado_general_final: null,
    resultado_post_servicio: '',
    foto_resultado: null,
  });

  const [plantillaFormula, setPlantillaFormula] = useState('');
  const [porosidades, setPorosidades] = useState([]);
  const [estadosGenerales, setEstadosGenerales] = useState([]);
  const [detalles, setDetalles] = useState([]);
  const [cargando, setCargando] = useState(false);
  const [error, setError] = useState('');
  const [fotoPreview, setFotoPreview] = useState(null);

  // Cargar datos iniciales
  useEffect(() => {
    cargarDatos();
  }, [turnoId]);

  const cargarDatos = async () => {
    setCargando(true);
    try {
      // Obtener turnos/detalles para este turno
      const turnoRes = await axios.get(`http://127.0.0.1:8000/api/gestion/turnos/${turnoId}/`);
      const turnoData = turnoRes.data;
      setDetalles(turnoData.detalles || []);

      // Si solo hay un detalle, lo preseleccionamos
      if (turnoData.detalles && turnoData.detalles.length === 1) {
        const detalle = turnoData.detalles[0];
        setFormulario(prev => ({
          ...prev,
          detalle_turno: detalle.id,
        }));
        // Cargar plantilla del servicio
        if (detalle.servicio_nombre) {
          cargarPlantillaServicio(detalle.id);
        }
      }

      // Cargar opciones de porosidad
      const porRes = await axios.get('http://127.0.0.1:8000/api/gestion/porosidades-cabello/');
      setPorosidades(porRes.data);

      // Cargar opciones de estado general
      const estRes = await axios.get('http://127.0.0.1:8000/api/gestion/estados-generales/');
      setEstadosGenerales(estRes.data);
    } catch (err) {
      console.error('Error cargando datos:', err);
      setError('Error al cargar los datos iniciales');
    } finally {
      setCargando(false);
    }
  };

  const cargarPlantillaServicio = async (detalleId) => {
    try {
      const res = await axios.get(
        `http://127.0.0.1:8000/api/gestion/fichas-tecnicas/`,
        {
          params: { detalle_turno: detalleId }
        }
      );
      if (res.data && res.data.length > 0) {
        setPlantillaFormula(res.data[0].formula_base_servicio || '');
      }
    } catch (err) {
      console.error('Error cargando plantilla:', err);
    }
  };

  const handleDetalleChange = (e) => {
    const detalleId = parseInt(e.target.value);
    setFormulario(prev => ({
      ...prev,
      detalle_turno: detalleId,
    }));
    cargarPlantillaServicio(detalleId);
  };

  const handleInputChange = (e) => {
    const { name, value } = e.target;
    setFormulario(prev => ({
      ...prev,
      [name]: value === '' ? null : value,
    }));
  };

  const handleFotoChange = (e) => {
    const archivo = e.target.files[0];
    if (archivo) {
      setFormulario(prev => ({
        ...prev,
        foto_resultado: archivo,
      }));
      // Preview
      const reader = new FileReader();
      reader.onload = (event) => {
        setFotoPreview(event.target.result);
      };
      reader.readAsDataURL(archivo);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setCargando(true);

    try {
      // Validaciones
      if (!formulario.detalle_turno) {
        setError('Debe seleccionar un servicio');
        setCargando(false);
        return;
      }

      if (!formulario.formula.trim()) {
        setError('La fórmula es obligatoria');
        setCargando(false);
        return;
      }

      // Preparar datos
      const datosEnvio = new FormData();
      datosEnvio.append('detalle_turno', formulario.detalle_turno);
      datosEnvio.append('formula', formulario.formula);
      datosEnvio.append('observaciones_proceso', formulario.observaciones_proceso || '');
      datosEnvio.append('porosidad_final', formulario.porosidad_final || '');
      datosEnvio.append('estado_general_final', formulario.estado_general_final || '');
      datosEnvio.append('resultado_post_servicio', formulario.resultado_post_servicio || '');
      
      if (formulario.foto_resultado) {
        datosEnvio.append('foto_resultado', formulario.foto_resultado);
      }

      // Crear ficha
      const res = await fichasTecnicasApi.crear(datosEnvio);
      
      // Notificar éxito
      if (onExito) {
        onExito(res);
      }

      // Limpiar formulario
      setFormulario({
        detalle_turno: null,
        formula: '',
        observaciones_proceso: '',
        porosidad_final: null,
        estado_general_final: null,
        resultado_post_servicio: '',
        foto_resultado: null,
      });
      setFotoPreview(null);

    } catch (err) {
      console.error('Error al crear ficha:', err);
      setError(err.response?.data?.detail || 'Error al registrar la ficha técnica');
    } finally {
      setCargando(false);
    }
  };

  if (cargando && detalles.length === 0) {
    return <div className="text-center py-10 text-gray-500 text-base">Cargando...</div>;
  }

  return (
    <div className="max-w-3xl mx-auto my-5 p-5 bg-white rounded-lg shadow-md">
      <div className="mb-7 border-b-4 border-pink-500 pb-4">
        <h2 className="text-2xl font-bold text-gray-800 m-0 mb-1">📋 Registrar Ficha Técnica</h2>
        <p className="text-gray-600 m-0 text-sm">Documenta la fórmula y resultados del servicio realizado</p>
      </div>

      {error && <div className="bg-red-100 text-red-800 p-3 rounded-md mb-5 border-l-4 border-red-800">{error}</div>}

      <form onSubmit={handleSubmit} className="flex flex-col gap-5">
        
        {/* Selección de Servicio */}
        {detalles.length > 0 && (
          <div className="flex flex-col gap-2">
            <label htmlFor="detalle_turno" className="font-semibold text-gray-800 text-sm">Servicio *</label>
            <select
              id="detalle_turno"
              value={formulario.detalle_turno || ''}
              onChange={handleDetalleChange}
              required
              className="p-3 border border-gray-300 rounded-md text-sm font-inherit transition-colors focus:outline-none focus:border-pink-500 focus:ring-2 focus:ring-pink-100"
            >
              <option value="">-- Selecciona un servicio --</option>
              {detalles.map(detalle => (
                <option key={detalle.id} value={detalle.id}>
                  {detalle.servicio_nombre}
                </option>
              ))}
            </select>
          </div>
        )}

        {/* Plantilla de Fórmula */}
        {plantillaFormula && (
          <div className="bg-gray-100 p-4 rounded-md border-l-4 border-blue-500">
            <p className="m-0 mb-1 text-gray-800"><strong>Estructura Base:</strong></p>
            <p className="m-0 text-gray-700">{plantillaFormula}</p>
          </div>
        )}

        {/* Fórmula */}
        <div className="flex flex-col gap-2">
          <label htmlFor="formula" className="font-semibold text-gray-800 text-sm">Fórmula Utilizada *</label>
          <textarea
            id="formula"
            name="formula"
            value={formulario.formula}
            onChange={handleInputChange}
            placeholder="Ej: Base: Colorante A 25%, Medios: Colorante B 50%, Oxidante: 25%"
            required
            className="p-3 border border-gray-300 rounded-md text-sm font-inherit transition-colors focus:outline-none focus:border-pink-500 focus:ring-2 focus:ring-pink-100 resize-vertical min-h-20"
            rows="3"
          />
        </div>

        {/* Observaciones del Proceso */}
        <div className="flex flex-col gap-2">
          <label htmlFor="observaciones_proceso" className="font-semibold text-gray-800 text-sm">Observaciones del Proceso</label>
          <textarea
            id="observaciones_proceso"
            name="observaciones_proceso"
            value={formulario.observaciones_proceso}
            onChange={handleInputChange}
            placeholder="Ej: Tiempo de exposición, reacciones del cabello, etc."
            className="p-3 border border-gray-300 rounded-md text-sm font-inherit transition-colors focus:outline-none focus:border-pink-500 focus:ring-2 focus:ring-pink-100 resize-vertical min-h-16"
            rows="2"
          />
        </div>

        {/* Porosidad Final */}
        <div className="flex flex-col gap-2">
          <label htmlFor="porosidad_final" className="font-semibold text-gray-800 text-sm">Porosidad Post-Servicio</label>
          <select
            id="porosidad_final"
            name="porosidad_final"
            value={formulario.porosidad_final || ''}
            onChange={handleInputChange}
            className="p-3 border border-gray-300 rounded-md text-sm font-inherit transition-colors focus:outline-none focus:border-pink-500 focus:ring-2 focus:ring-pink-100"
          >
            <option value="">-- Selecciona porosidad --</option>
            {porosidades.map(poro => (
              <option key={poro.id} value={poro.id}>
                {poro.nombre}
              </option>
            ))}
          </select>
        </div>

        {/* Estado General Final */}
        <div className="flex flex-col gap-2">
          <label htmlFor="estado_general_final" className="font-semibold text-gray-800 text-sm">Estado General Post-Servicio</label>
          <select
            id="estado_general_final"
            name="estado_general_final"
            value={formulario.estado_general_final || ''}
            onChange={handleInputChange}
            className="p-3 border border-gray-300 rounded-md text-sm font-inherit transition-colors focus:outline-none focus:border-pink-500 focus:ring-2 focus:ring-pink-100"
          >
            <option value="">-- Selecciona estado --</option>
            {estadosGenerales.map(est => (
              <option key={est.id} value={est.id}>
                {est.nombre}
              </option>
            ))}
          </select>
        </div>

        {/* Resultado Post-Servicio */}
        <div className="flex flex-col gap-2">
          <label htmlFor="resultado_post_servicio" className="font-semibold text-gray-800 text-sm">Resultado y Observaciones Finales</label>
          <textarea
            id="resultado_post_servicio"
            name="resultado_post_servicio"
            value={formulario.resultado_post_servicio}
            onChange={handleInputChange}
            placeholder="Descripción del resultado final del servicio"
            className="p-3 border border-gray-300 rounded-md text-sm font-inherit transition-colors focus:outline-none focus:border-pink-500 focus:ring-2 focus:ring-pink-100 resize-vertical min-h-20"
            rows="3"
          />
        </div>

        {/* Foto de Resultado */}
        <div className="flex flex-col gap-2">
          <label htmlFor="foto_resultado" className="font-semibold text-gray-800 text-sm">Foto del Resultado</label>
          <input
            id="foto_resultado"
            type="file"
            accept="image/*"
            onChange={handleFotoChange}
            className="p-3 border border-gray-300 rounded-md text-sm font-inherit"
          />
          {fotoPreview && (
            <div className="mt-2.5 max-w-xs">
              <img src={fotoPreview} alt="Preview" className="w-full rounded-md border-2 border-pink-500" />
            </div>
          )}
        </div>

        {/* Botones */}
        <div className="flex gap-2.5 mt-5 pt-5 border-t border-gray-200">
          <button
            type="submit"
            disabled={cargando}
            className="px-6 py-3 bg-pink-500 text-white border-none rounded-md text-sm font-semibold cursor-pointer transition-all flex-1 hover:bg-pink-600 hover:translate-y-px disabled:bg-gray-400 disabled:cursor-not-allowed disabled:transform-none disabled:shadow-none"
          >
            {cargando ? 'Registrando...' : '✓ Registrar Ficha'}
          </button>
          <button
            type="button"
            onClick={onCancelar}
            disabled={cargando}
            className="px-6 py-3 bg-gray-200 text-gray-800 border-none rounded-md text-sm font-semibold cursor-pointer transition-all hover:bg-gray-300 disabled:bg-gray-200 disabled:cursor-not-allowed"
          >
            Cancelar
          </button>
        </div>
      </form>
    </div>
  );
};

export default RegistroFichaTecnica;
