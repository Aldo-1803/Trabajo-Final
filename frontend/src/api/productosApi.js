import axios from 'axios';

const API_BASE = 'http://127.0.0.1:8000/api/gestion';

const getAuthHeaders = () => {
    const token = localStorage.getItem('access_token');
    return { 'Authorization': `Bearer ${token}` };
};

const productosApi = {
    // --- PRODUCTOS ---
    async obtenerProductos() {
        try {
            const res = await axios.get(`${API_BASE}/productos/`, {
                headers: getAuthHeaders()
            });
            return res.data;
        } catch (error) {
            console.error('Error obteniendo productos:', error);
            throw error;
        }
    },

    async obtenerProducto(id) {
        try {
            const res = await axios.get(`${API_BASE}/productos/${id}/`, {
                headers: getAuthHeaders()
            });
            return res.data;
        } catch (error) {
            console.error('Error obteniendo producto:', error);
            throw error;
        }
    },

    async crearProducto(datos) {
        try {
            const res = await axios.post(`${API_BASE}/productos/`, datos, {
                headers: getAuthHeaders()
            });
            return res.data;
        } catch (error) {
            console.error('Error creando producto:', error);
            throw error;
        }
    },

    async actualizarProducto(id, datos) {
        try {
            const res = await axios.put(`${API_BASE}/productos/${id}/`, datos, {
                headers: getAuthHeaders()
            });
            return res.data;
        } catch (error) {
            console.error('Error actualizando producto:', error);
            throw error;
        }
    },

    async eliminarProducto(id) {
        try {
            await axios.delete(`${API_BASE}/productos/${id}/`, {
                headers: getAuthHeaders()
            });
        } catch (error) {
            console.error('Error eliminando producto:', error);
            throw error;
        }
    },

    // --- ALERTAS DE STOCK ---
    async obtenerStockBajo() {
        try {
            const res = await axios.get(`${API_BASE}/productos/stock_bajo/`, {
                headers: getAuthHeaders()
            });
            return res.data;
        } catch (error) {
            console.error('Error obteniendo alertas de stock:', error);
            throw error;
        }
    },

    // --- RECOMENDACIONES INTELIGENTES ---
    async obtenerProductosSugeridos() {
        try {
            const res = await axios.get(`${API_BASE}/productos/sugeridos-cliente/`, {
                headers: getAuthHeaders()
            });
            return res.data;
        } catch (error) {
            if (error.response?.status === 404) {
                return {
                    error: 'Sin diagnósticos previos',
                    productos_sugeridos: [],
                    motivo_sugerencia: ''
                };
            }
            console.error('Error obteniendo productos sugeridos:', error);
            throw error;
        }
    },

    // --- CATEGORÍAS ---
    async obtenerCategorias() {
        try {
            const res = await axios.get(`${API_BASE}/categorias-productos/`, {
                headers: getAuthHeaders()
            });
            return res.data;
        } catch (error) {
            console.error('Error obteniendo categorías:', error);
            throw error;
        }
    },

    async crearCategoria(datos) {
        try {
            const res = await axios.post(`${API_BASE}/categorias-productos/`, datos, {
                headers: getAuthHeaders()
            });
            return res.data;
        } catch (error) {
            console.error('Error creando categoría:', error);
            throw error;
        }
    },

    async actualizarCategoria(id, datos) {
        try {
            const res = await axios.put(`${API_BASE}/categorias-productos/${id}/`, datos, {
                headers: getAuthHeaders()
            });
            return res.data;
        } catch (error) {
            console.error('Error actualizando categoría:', error);
            throw error;
        }
    },

    async eliminarCategoria(id) {
        try {
            await axios.delete(`${API_BASE}/categorias-productos/${id}/`, {
                headers: getAuthHeaders()
            });
        } catch (error) {
            console.error('Error eliminando categoría:', error);
            throw error;
        }
    }
};

export default productosApi;
