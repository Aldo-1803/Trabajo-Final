import axios from 'axios';

const API_BASE_URL = 'http://127.0.0.1:8000/api/gestion';

const token = localStorage.getItem('access_token');

const API_CLIENT = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Authorization': `Bearer ${token}`,
    'Content-Type': 'application/json',
  },
});

// Actualizar token cuando cambia
export const setAuthToken = (newToken) => {
  if (newToken) {
    API_CLIENT.defaults.headers['Authorization'] = `Bearer ${newToken}`;
  }
};

// FICHAS TÉCNICAS - CRUD
export const fichasTecnicasApi = {
  /**
   * Obtener todas las fichas técnicas (solo admins/staff)
   */
  obtenerTodas: async () => {
    try {
      const res = await API_CLIENT.get('/fichas-tecnicas/');
      return res.data;
    } catch (error) {
      console.error('Error al obtener fichas técnicas:', error);
      throw error;
    }
  },

  /**
   * Obtener fichas técnicas de un turno específico
   * @param {number} turnoId - ID del turno
   */
  obtenerPorTurno: async (turnoId) => {
    try {
      const res = await API_CLIENT.get(`/fichas-tecnicas/por_turno/?turno_id=${turnoId}`);
      return res.data;
    } catch (error) {
      console.error(`Error al obtener fichas del turno ${turnoId}:`, error);
      throw error;
    }
  },

  /**
   * Obtener las fichas técnicas creadas por el profesional autenticado
   */
  obtenerMisFichas: async () => {
    try {
      const res = await API_CLIENT.get('/fichas-tecnicas/mis_fichas/');
      return res.data;
    } catch (error) {
      console.error('Error al obtener mis fichas:', error);
      throw error;
    }
  },

  /**
   * Crear una nueva ficha técnica
   * @param {object} data - Datos de la ficha
   */
  crear: async (data) => {
    try {
      const res = await API_CLIENT.post('/fichas-tecnicas/', data);
      return res.data;
    } catch (error) {
      console.error('Error al crear ficha técnica:', error);
      throw error;
    }
  },

  /**
   * Obtener detalle de una ficha técnica
   * @param {number} id - ID de la ficha
   */
  obtener: async (id) => {
    try {
      const res = await API_CLIENT.get(`/fichas-tecnicas/${id}/`);
      return res.data;
    } catch (error) {
      console.error(`Error al obtener ficha ${id}:`, error);
      throw error;
    }
  },

  /**
   * Actualizar una ficha técnica
   * @param {number} id - ID de la ficha
   * @param {object} data - Datos a actualizar
   */
  actualizar: async (id, data) => {
    try {
      const res = await API_CLIENT.put(`/fichas-tecnicas/${id}/`, data);
      return res.data;
    } catch (error) {
      console.error(`Error al actualizar ficha ${id}:`, error);
      throw error;
    }
  },

  /**
   * Eliminar una ficha técnica
   * @param {number} id - ID de la ficha
   */
  eliminar: async (id) => {
    try {
      await API_CLIENT.delete(`/fichas-tecnicas/${id}/`);
    } catch (error) {
      console.error(`Error al eliminar ficha ${id}:`, error);
      throw error;
    }
  },

  /**
   * Subir foto de resultado
   * @param {number} id - ID de la ficha
   * @param {File} archivo - Archivo de imagen
   */
  subirFoto: async (id, archivo) => {
    try {
      const formData = new FormData();
      formData.append('foto_resultado', archivo);
      
      const res = await API_CLIENT.patch(`/fichas-tecnicas/${id}/`, formData, {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
      });
      return res.data;
    } catch (error) {
      console.error(`Error al subir foto en ficha ${id}:`, error);
      throw error;
    }
  },
};

export default fichasTecnicasApi;
