import Swal from 'sweetalert2';
import toast from 'react-hot-toast';

/**
 * Muestra un diálogo de confirmación personalizado
 * @param {Object} config - Configuración del diálogo
 * @param {string} config.title - Título del diálogo
 * @param {string} config.text - Texto del diálogo (opcional)
 * @param {string} config.confirmButtonText - Texto del botón confirmar (default: "Sí")
 * @param {string} config.cancelButtonText - Texto del botón cancelar (default: "Cancelar")
 * @returns {Promise} Resultado con propiedad isConfirmed
 */
export const confirmarAccion = async ({
    title = "¿Estás seguro?",
    text = "",
    confirmButtonText = "Sí",
    cancelButtonText = "Cancelar"
} = {}) => {
    return await Swal.fire({
        title,
        text,
        icon: 'warning',
        showCancelButton: true,
        confirmButtonColor: '#817773',
        cancelButtonColor: '#D5D1CC',
        confirmButtonText,
        cancelButtonText,
        backdrop: true,
        allowOutsideClick: false
    });
};

/**
 * Objeto con funciones de notificación para diferentes tipos de mensajes
 */
export const notify = {
    /**
     * Muestra una notificación de éxito
     * @param {string} message - Mensaje a mostrar
     * @param {Object} options - Opciones adicionales (opcional)
     */
    success: (message, options = {}) => {
        toast.success(message, {
            duration: 4000,
            position: 'top-right',
            style: { 
                background: '#E8F5E8', 
                color: '#2E7D2E',
                border: '1px solid #2E7D2E'
            },
            ...options
        });
    },

    /**
     * Muestra una notificación de error
     * @param {string} message - Mensaje a mostrar
     * @param {Object} options - Opciones adicionales (opcional)
     */
    error: (message, options = {}) => {
        toast.error(message, {
            duration: 4000,
            position: 'top-right',
            style: { 
                background: '#FFE8E8', 
                color: '#C73E3E',
                border: '1px solid #C73E3E'
            },
            ...options
        });
    },

    /**
     * Muestra una notificación de información
     * @param {string} message - Mensaje a mostrar
     * @param {Object} options - Opciones adicionales (opcional)
     */
    info: (message, options = {}) => {
        toast((t) => (
            <div style={{ color: '#817773', fontWeight: 'bold' }}>
                ℹ️ {message}
            </div>
        ), {
            duration: 4000,
            position: 'top-right',
            ...options
        });
    },

    /**
     * Muestra una notificación de carga
     * @param {string} message - Mensaje a mostrar
     * @returns {string} Toast ID para poder actualizarlo después
     */
    loading: (message) => {
        return toast.loading(message, {
            position: 'top-right'
        });
    },

    /**
     * Actualiza un toast de carga existente
     * @param {string} toastId - ID del toast a actualizar
     * @param {string} message - Nuevo mensaje
     * @param {string} type - Tipo de notificación ('success', 'error', 'info')
     */
    update: (toastId, message, type = 'success') => {
        toast.dismiss(toastId);
        notify[type](message);
    }
};

export default { confirmarAccion, notify };