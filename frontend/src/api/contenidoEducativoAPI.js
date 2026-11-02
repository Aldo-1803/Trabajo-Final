import axios from 'axios';

const API_BASE = 'http://127.0.0.1:8000/api/gestion/contenido-educativo';

/**
 * Obtiene el token de autenticación del localStorage
 * @returns {Object} Headers con Authorization
 */
const getAuthHeaders = () => {
    const token = localStorage.getItem('access_token');
    return {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json'
    };
};

/**
 * Manejo centralizado de errores
 * @param {Error} error - El error de axios
 * @throws {Error} - Lanza el error procesado
 */
const handleError = (error) => {
    if (error.response?.status === 401) {
        // Token expirado o inválido
        localStorage.removeItem('access_token');
        localStorage.removeItem('refresh_token');
        window.location.href = '/login';
    }
    console.error('Error en API de Contenido Educativo:', error);
    throw error;
};

/**
 * API de Contenido Educativo
 * Centraliza todas las peticiones relacionadas con contenido educativo
 */
export const contenidoEducativoAPI = {
    /**
     * Obtiene todos los contenidos publicados
     * @param {Object} params - Parámetros de filtrado
     * @param {string} params.tipo - Filtrar por tipo (articulo, video, tutorial, consejo)
     * @param {string} params.autor - Filtrar por ID de autor
     * @param {string} params.search - Buscar por título, tags o descripción
     * @param {string} params.ordering - Ordenamiento (-fecha_publicacion, fecha_publicacion)
     * @returns {Promise<Array>} Lista de contenidos
     */
    getPublicados: async (params = {}) => {
        try {
            const response = await axios.get(`${API_BASE}/?estado=PUBLICADO`, {
                headers: getAuthHeaders(),
                params
            });
            return response.data.results || response.data;
        } catch (error) {
            handleError(error);
        }
    },

    /**
     * Obtiene un contenido específico por ID
     * @param {number} id - ID del contenido
     * @returns {Promise<Object>} Objeto de contenido con detalles completos
     */
    getById: async (id) => {
        try {
            if (!id || typeof id !== 'number') {
                throw new Error('ID de contenido inválido');
            }
            const response = await axios.get(`${API_BASE}/${id}/`, {
                headers: getAuthHeaders()
            });
            return response.data;
        } catch (error) {
            handleError(error);
        }
    },

    /**
     * Da like a un contenido (o quita si ya lo tiene)
     * @param {number} id - ID del contenido
     * @returns {Promise<Object>} Respuesta con total_likes actualizado
     */
    like: async (id) => {
        try {
            if (!id || typeof id !== 'number') {
                throw new Error('ID de contenido inválido');
            }
            const response = await axios.post(`${API_BASE}/${id}/like/`, {}, {
                headers: getAuthHeaders()
            });
            return response.data;
        } catch (error) {
            handleError(error);
        }
    },

    /**
     * Guarda/desguarda un contenido
     * @param {number} id - ID del contenido
     * @returns {Promise<Object>} Respuesta de la operación
     */
    guardar: async (id) => {
        try {
            if (!id || typeof id !== 'number') {
                throw new Error('ID de contenido inválido');
            }
            const response = await axios.post(`${API_BASE}/${id}/guardar/`, {}, {
                headers: getAuthHeaders()
            });
            return response.data;
        } catch (error) {
            handleError(error);
        }
    },

    /**
     * Obtiene los contenidos guardados del usuario actual
     * @param {Object} params - Parámetros adicionales de filtrado
     * @returns {Promise<Array>} Lista de contenidos guardados
     */
    getMisGuardados: async (params = {}) => {
        try {
            const response = await axios.get(`${API_BASE}/?guardado=true`, {
                headers: getAuthHeaders(),
                params
            });
            return response.data.results || response.data;
        } catch (error) {
            handleError(error);
        }
    },

    /**
     * Obtiene los contenidos a los que el usuario ha dado like
     * @param {Object} params - Parámetros adicionales de filtrado
     * @returns {Promise<Array>} Lista de contenidos con like
     */
    getMisLikes: async (params = {}) => {
        try {
            const response = await axios.get(`${API_BASE}/?me_gusta=true`, {
                headers: getAuthHeaders(),
                params
            });
            return response.data.results || response.data;
        } catch (error) {
            handleError(error);
        }
    },

    /**
     * Obtiene estadísticas del contenido educativo
     * @returns {Promise<Object>} Objeto con estadísticas (total_articulos, autores, etc)
     */
    getEstadisticas: async () => {
        try {
            const response = await axios.get(`${API_BASE}/estadisticas/`, {
                headers: getAuthHeaders()
            });
            return response.data;
        } catch (error) {
            handleError(error);
        }
    }
};

export default contenidoEducativoAPI;
