import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';
import { confirmarAccion, notify } from '../../utils/notificaciones';
import { useSession } from '../../context/SessionContext';

const GestionProductos = () => {
    const { hasPermission } = useSession();
    const canViewStock = hasPermission('gestion.view_stock');
    const canManageStock = hasPermission('gestion.manage_stock');
    const canManageProducts = hasPermission('gestion.manage_products');
    const canManagePrices = hasPermission('gestion.manage_prices');
    const canManagePromotions = hasPermission('gestion.manage_promotions');
    const canEditProduct = canManageProducts || canManagePrices;
    // --- ESTADOS ---
    const [productos, setProductos] = useState([]);
    const [categorias, setCategorias] = useState([]);
    const [loading, setLoading] = useState(true);
    const [modalAbierto, setModalAbierto] = useState(false);
    const [modoEdicion, setModoEdicion] = useState(false);
    const [tabActiva, setTabActiva] = useState('catalogo'); // 'catalogo' | 'alertas' | 'combos'
    const [productosStockBajo, setProductosStockBajo] = useState([]);
    const [combosSugeridos, setCombosSugeridos] = useState([]);
    const [loadingCombos, setLoadingCombos] = useState(false);
    const [inventarioProducto, setInventarioProducto] = useState(null);
    const [movimientos, setMovimientos] = useState([]);
    const [loadingMovimientos, setLoadingMovimientos] = useState(false);
    const [stockCommand, setStockCommand] = useState({
        quantity: '',
        delta: '',
        movementId: '',
        reason_code: 'MANUAL_D3',
        note: ''
    });
    const [categoriaForm, setCategoriaForm] = useState({
        id: null,
        nombre: '',
        descripcion: '',
        activo: true
    });
    const [comboEdiciones, setComboEdiciones] = useState({});
    const [comboForm, setComboForm] = useState({
        nombre: '',
        descripcion: '',
        descuento_porcentaje: 10,
        dias_vigencia: 15,
        productos: []
    });
    
    // Estado del Formulario
    const [form, setForm] = useState({
        id: null,
        sku: '',
        nombre: '',
        marca: '',
        categoria: '',
        descripcion: '',
        material_principal: '',
        proposito_uso: '',
        precio: '',
        imagen: null,
        imagen_url: '', // Solo para lectura (URL completa del servidor)
        estado_publicacion: 'PUBLICADO',
        compatibilidad: 'TODO',
        activo: true
    });
    
    // Estado para manejar múltiples imágenes
    const [imagenesSubidas, setImagenesSubidas] = useState([]);

    const navigate = useNavigate();

    // --- OPCIONES DE COMPATIBILIDAD ---
    const opcionesCompatibilidad = [
        { value: 'TODO', label: 'Todos los tipos' },
        { value: 'LACIO', label: 'Cabello Lacio' },
        { value: 'RIZADO', label: 'Cabello Rizado/Afro' },
        { value: 'DANADO', label: 'Cabello Dañado' },
        { value: 'GRASO', label: 'Cuero Cabelludo Graso' },
        { value: 'SECO', label: 'Cuero Cabelludo Seco' },
    ];

    const opcionesMaterialPrincipal = [
        { value: 'SATEN', label: 'Satén' },
        { value: 'MICROFIBRA', label: 'Microfibra' },
        { value: 'MADERA', label: 'Madera' },
        { value: 'PLASTICO', label: 'Plástico' },
    ];

    const opcionesPropositoUso = [
        { value: 'DORMIR', label: 'Dormir' },
        { value: 'STYLING', label: 'Styling (Peinado)' },
        { value: 'HIGIENE', label: 'Higiene' },
        { value: 'SECADO', label: 'Secado' },
    ];

    const opcionesEstadoPublicacion = [
        { value: 'PUBLICADO', label: 'Publicado' },
        { value: 'BORRADOR', label: 'Borrador' },
        { value: 'DISCONTINUADO', label: 'Discontinuado' },
    ];

    const getStockDisponible = (prod) => {
        const stockDisponible = Number(prod?.stock_disponible);
        if (Number.isFinite(stockDisponible)) {
            return stockDisponible;
        }
        return prod?.available === true ? 1 : 0;
    };

    // --- CARGA INICIAL ---
    useEffect(() => {
        cargarProductos();
        cargarCategorias();
        if (canViewStock) cargarProductosStockBajo();
        if (canManagePromotions) cargarCombosSugeridos();
        // Las funciones de carga sólo dependen del snapshot actual de capacidades.
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [canViewStock, canManagePromotions]);

    const domainError = (error, fallback) => {
        if (error?.response?.status === 403) {
            return 'No tienes permiso para realizar esta operación.';
        }
        const payload = error?.response?.data;
        return payload?.error?.detail || payload?.error || payload?.detail || fallback;
    };

    const newIdempotencyKey = (operation) => (
        `frontend:${operation}:${Date.now()}:${Math.random().toString(16).slice(2)}`
    );

    const cargarProductos = async () => {
        setLoading(true);
        try {
            const token = localStorage.getItem('access_token');
            const res = await axios.get('http://127.0.0.1:8000/api/gestion/productos/', {
                headers: { 'Authorization': `Bearer ${token}` }
            });
            setProductos(res.data);
        } catch (error) {
            console.error("Error al cargar productos", error);
            notify.error("Error al cargar productos");
        } finally {
            setLoading(false);
        }
    };

    const cargarCategorias = async () => {
        try {
            const token = localStorage.getItem('access_token');
            const res = await axios.get('http://127.0.0.1:8000/api/gestion/categorias-productos/', {
                headers: { 'Authorization': `Bearer ${token}` }
            });
            setCategorias(res.data);
        } catch (error) {
            console.error("Error al cargar categorías", error);
        }
    };

    const cargarProductosStockBajo = async () => {
        if (!canViewStock) return;
        try {
            const token = localStorage.getItem('access_token');
            const res = await axios.get('http://127.0.0.1:8000/api/gestion/productos/stock_bajo/', {
                headers: { 'Authorization': `Bearer ${token}` }
            });
            setProductosStockBajo(res.data.productos || []);
        } catch (error) {
            console.error("Error al cargar alertas de stock", error);
        }
    };

    const cargarCombosSugeridos = async () => {
        if (!canManagePromotions) return;
        try {
            setLoadingCombos(true);
            const token = localStorage.getItem('access_token');
            const res = await axios.get('http://127.0.0.1:8000/api/gestion/promociones/sugerencias/', {
                headers: { 'Authorization': `Bearer ${token}` }
            });
            const sugerencias = Array.isArray(res.data) ? res.data : (res.data?.results || []);
            setCombosSugeridos(sugerencias);
            const ediciones = {};
            sugerencias.forEach((combo) => {
                ediciones[combo.id] = {
                    nombre: combo.nombre,
                    descripcion: combo.descripcion,
                    descuento_porcentaje: combo.descuento_porcentaje
                };
            });
            setComboEdiciones(ediciones);
        } catch (error) {
            console.error('Error al cargar combos sugeridos', error);
            notify.error('No se pudieron cargar las sugerencias de combos');
        } finally {
            setLoadingCombos(false);
        }
    };

    const actualizarEdicionCombo = (id, campo, valor) => {
        setComboEdiciones((prev) => ({
            ...prev,
            [id]: {
                ...prev[id],
                [campo]: valor
            }
        }));
    };

    const publicarCombo = async (comboId) => {
        try {
            const token = localStorage.getItem('access_token');
            const payload = comboEdiciones[comboId] || {};
            await axios.post(
                `http://127.0.0.1:8000/api/gestion/promociones/${comboId}/publicar/`,
                payload,
                { headers: { 'Authorization': `Bearer ${token}` } }
            );
            notify.success('Combo publicado correctamente.');
            cargarCombosSugeridos();
        } catch (error) {
            console.error('Error al publicar combo', error);
            notify.error('No se pudo publicar el combo.');
        }
    };

    const rechazarCombo = async (comboId) => {
        const result = await confirmarAccion({
            title: '¿Rechazar sugerencia?',
            text: 'Esta sugerencia se descartará.',
            confirmButtonText: 'Sí, rechazar'
        });
        if (!result.isConfirmed) return;

        try {
            const token = localStorage.getItem('access_token');
            await axios.post(
                `http://127.0.0.1:8000/api/gestion/promociones/${comboId}/rechazar/`,
                {},
                { headers: { 'Authorization': `Bearer ${token}` } }
            );
            notify.success('Combo rechazado.');
            cargarCombosSugeridos();
        } catch (error) {
            console.error('Error al rechazar combo', error);
            notify.error('No se pudo rechazar el combo.');
        }
    };

    const toggleProductoCombo = (productoId) => {
        setComboForm((prev) => {
            const existe = prev.productos.includes(productoId);
            const productos = existe
                ? prev.productos.filter((id) => id !== productoId)
                : [...prev.productos, productoId];
            return { ...prev, productos };
        });
    };

    const crearComboManual = async (e) => {
        e.preventDefault();

        if (!comboForm.nombre.trim()) {
            notify.error('El nombre del combo es requerido.');
            return;
        }
        if (comboForm.productos.length < 2) {
            notify.error('Selecciona al menos 2 productos para el combo.');
            return;
        }

        try {
            const token = localStorage.getItem('access_token');
            const hoy = new Date();
            const fechaInicio = hoy.toISOString().slice(0, 10);
            const fechaFin = new Date(hoy);
            fechaFin.setDate(fechaFin.getDate() + Number(comboForm.dias_vigencia || 15));

            await axios.post(
                'http://127.0.0.1:8000/api/gestion/promociones/',
                {
                    nombre: comboForm.nombre.trim(),
                    descripcion: comboForm.descripcion.trim() || 'Combo creado manualmente',
                    tipo: 'COMBO',
                    descuento_porcentaje: Number(comboForm.descuento_porcentaje || 10),
                    fecha_inicio: fechaInicio,
                    fecha_fin: fechaFin.toISOString().slice(0, 10),
                    is_active: true,
                    es_sugerencia_automatica: false,
                    estado_sugerencia: 'ACEPTADA',
                    productos: comboForm.productos
                },
                { headers: { 'Authorization': `Bearer ${token}` } }
            );

            notify.success('Combo creado y publicado.');
            setComboForm({
                nombre: '',
                descripcion: '',
                descuento_porcentaje: 10,
                dias_vigencia: 15,
                productos: []
            });
        } catch (error) {
            console.error('Error creando combo manual', error);
            notify.error('No se pudo crear el combo manual.');
        }
    };

    // --- MANEJADORES DEL FORMULARIO ---
    const handleChange = (e) => {
        const { name, type, checked, value } = e.target;
        setForm({ 
            ...form, 
            [name]: type === 'checkbox' ? checked : value 
        });
    };

    // Manejar carga de imágenes (múltiples)
    const handleSubirImagen = async (e) => {
        const archivos = e.target.files;
        if (!archivos || archivos.length === 0) return;

        const nuevasImagenes = [];

        for (let i = 0; i < archivos.length; i++) {
            const archivo = archivos[i];

            // Validar que sea imagen
            if (!archivo.type.startsWith('image/')) {
                notify.error(`${archivo.name} no es una imagen válida`);
                continue;
            }

            // Validar tamaño (máx 5MB)
            if (archivo.size > 5 * 1024 * 1024) {
                notify.error(`${archivo.name} es muy grande (máx 5MB)`);
                continue;
            }

            nuevasImagenes.push({
                id: Date.now() + i, // ID temporal para identificar en lista
                archivo: archivo,
                preview: URL.createObjectURL(archivo)
            });
        }

        if (nuevasImagenes.length > 0) {
            setImagenesSubidas([...imagenesSubidas, ...nuevasImagenes]);
            notify.success(`${nuevasImagenes.length} imagen(es) seleccionada(s) para subir`);
        }
        
        e.target.value = ''; // Reset input
    };

    // Eliminar imagen de la lista a subir (nueva o existente)
    const eliminarImagenSubida = async (id) => {
        const imagenAEliminar = imagenesSubidas.find(img => img.id === id);
        
        // Si es una imagen existente, eliminarla del servidor
        if (imagenAEliminar?.esExistente) {
            const result = await confirmarAccion({
                title: '¿Eliminar imagen?',
                text: 'Esta acción no se puede deshacer',
                confirmButtonText: 'Sí, eliminar'
            });
            
            if (!result.isConfirmed) return;
            
            try {
                const token = localStorage.getItem('access_token');
                await axios.delete(
                    `http://127.0.0.1:8000/api/gestion/imagenes-productos/${imagenAEliminar.productoImagenId}/`,
                    { headers: { 'Authorization': `Bearer ${token}` } }
                );
                notify.success('Imagen eliminada correctamente');
            } catch (error) {
                console.error('Error al eliminar imagen:', error);
                notify.error('No se pudo eliminar la imagen');
                return;
            }
        } else if (imagenAEliminar?.preview) {
            // Si es una imagen nueva, solo liberar la URL del objeto
            URL.revokeObjectURL(imagenAEliminar.preview);
        }
        
        setImagenesSubidas(imagenesSubidas.filter(img => img.id !== id));
    };

    // Eliminar imagen principal (para edición)
    const eliminarImagen = () => {
        setForm({ ...form, imagen: null, imagen_url: '' });
        notify.success('Imagen principal eliminada');
    };

    const abrirModal = (producto = null) => {
        if (!canEditProduct || (!producto && !(canManageProducts && canManagePrices))) {
            notify.error('No tienes permisos suficientes para esta operación.');
            return;
        }
        if (producto) {
            setModoEdicion(true);
            setForm(producto);
            
            // Si el producto tiene imágenes adicionales, cargarlas para mostrar en el modal
            // PERO NO LA PRIMERA (que es la imagen principal)
            if (producto.imagenes && producto.imagenes.length > 1) {
                const imagenesExistentes = producto.imagenes.slice(1).map((img, idx) => ({
                    id: `existing-${img.id}`, // ID único para distinguir de nuevas
                    url: img.imagen_url, // URL de la imagen existente
                    orden: img.orden,
                    productoImagenId: img.id, // ID en la base de datos
                    esExistente: true // Flag para saber que ya existe en BD
                }));
                setImagenesSubidas(imagenesExistentes);
            } else {
                setImagenesSubidas([]);
            }
        } else {
            setModoEdicion(false);
            setForm({
                id: null,
                sku: '',
                nombre: '',
                marca: '',
                categoria: '',
                descripcion: '',
                material_principal: '',
                proposito_uso: '',
                precio: '',
                imagen: null,
                imagen_url: '',
                estado_publicacion: 'PUBLICADO',
                compatibilidad: 'TODO',
                activo: true
            });
            setImagenesSubidas([]);
        }
        setModalAbierto(true);
    };

    const cerrarModal = () => {
        setModalAbierto(false);
    };

    // --- ACCIONES CRUD ---
    const guardarProducto = async (e) => {
        e.preventDefault();
        const token = localStorage.getItem('access_token');
        const headers = { 'Authorization': `Bearer ${token}` };

        // Validaciones
        if (canManageProducts && (!form.nombre || !form.nombre.trim())) {
            notify.error("El nombre del producto es requerido.");
            return;
        }

        if (canManagePrices && (!form.precio || parseFloat(form.precio) <= 0)) {
            notify.error("El precio debe ser mayor a 0.");
            return;
        }

        if (canManageProducts && (!form.categoria || form.categoria === '')) {
            notify.error("Por favor selecciona una categoría.");
            return;
        }

        // La imagen es opcional

        // Convertir tipos de datos
        const categoriaId = canManageProducts ? parseInt(form.categoria) : null;
        if (canManageProducts && isNaN(categoriaId)) {
            notify.error("Categoría inválida.");
            return;
        }

        const precioNum = parseFloat(form.precio);

        // Preparar FormData para enviar archivo principal
        const imagenPrincipal = form.imagen instanceof File
            ? form.imagen
            : (imagenesSubidas.length > 0 ? imagenesSubidas[0].archivo : null);

        const formData = new FormData();
        if (canManageProducts) {
            if (form.sku && form.sku.trim()) {
                formData.append('sku', form.sku.trim());
            }
            formData.append('nombre', form.nombre.trim());
            formData.append('marca', form.marca?.trim() || '');
            formData.append('categoria', categoriaId);
            formData.append('descripcion', form.descripcion || '');
            formData.append('material_principal', form.material_principal || '');
            formData.append('proposito_uso', form.proposito_uso || '');
            formData.append('estado_publicacion', form.estado_publicacion || 'PUBLICADO');
            formData.append('compatibilidad', form.compatibilidad || 'TODO');
            formData.append('activo', form.activo === true || form.activo === 'true');
        }
        if (canManagePrices) formData.append('precio', precioNum);
        
        // Agregar imagen principal si hay una nueva
        if (canManageProducts && imagenPrincipal) {
            formData.append('imagen', imagenPrincipal);
        }

        try {
            let productoId = form.id;
            let mensaje = "";
            
            if (modoEdicion) {
                await axios.patch(`http://127.0.0.1:8000/api/gestion/productos/${form.id}/`, formData, { headers });
                mensaje = "Producto actualizado correctamente.";
            } else {
                const response = await axios.post('http://127.0.0.1:8000/api/gestion/productos/', formData, { headers });
                productoId = response.data.id;
                mensaje = "Producto creado exitosamente.";
            }
            
            // Ahora subir las imágenes adicionales si existen (solo las nuevas)
            const imagenesNuevas = imagenesSubidas
                .filter(img => !img.esExistente)
                .filter(img => img.archivo && img.archivo !== imagenPrincipal);
            
            if (canManageProducts && imagenesNuevas.length > 0) {
                for (let i = 0; i < imagenesNuevas.length; i++) {
                    const imagenData = new FormData();
                    imagenData.append('imagen', imagenesNuevas[i].archivo);
                    imagenData.append('orden', imagenesSubidas.length + i); // Ordenar después de las existentes
                    imagenData.append('producto', productoId);
                    
                    try {
                        await axios.post(`http://127.0.0.1:8000/api/gestion/imagenes-productos/`, imagenData, { headers });
                    } catch (imgError) {
                        console.error(`Error al subir imagen ${i + 1}:`, imgError);
                        notify.warning(`La imagen ${i + 1} (${imagenesNuevas[i].archivo.name}) no se pudo subir correctamente.`);
                    }
                }
            }
            
            notify.success(mensaje);
            cerrarModal();
            setImagenesSubidas([]);
            
            // Pequeño delay para asegurar que el servidor completó la operación
            setTimeout(() => {
                cargarProductos();
                if (canViewStock) cargarProductosStockBajo();
            }, 500);
        } catch (error) {
            console.error('Error completo:', error);
            console.error('Response data:', error.response?.data);
            const detalles = error.response?.data;
            let msg = "Error al guardar el producto.";
            
            // Mostrar el primer error específico del campo
            if (detalles) {
                for (let key in detalles) {
                    if (Array.isArray(detalles[key])) {
                        msg = `${key}: ${detalles[key][0]}`;
                    } else if (typeof detalles[key] === 'object') {
                        msg = `${key}: ${JSON.stringify(detalles[key])}`;
                    } else {
                        msg = `${key}: ${detalles[key]}`;
                    }
                    break;
                }
            }
            
            notify.error(domainError(error, msg));
        }
    };

    const cargarMovimientos = async (productoId) => {
        if (!canViewStock) {
            setMovimientos([]);
            return;
        }
        setLoadingMovimientos(true);
        try {
            const token = localStorage.getItem('access_token');
            const response = await axios.get(
                `http://127.0.0.1:8000/api/gestion/productos/${productoId}/stock-movements/`,
                { headers: { 'Authorization': `Bearer ${token}` } }
            );
            setMovimientos(response.data?.results || []);
        } catch (error) {
            notify.error(domainError(error, 'No se pudieron consultar los movimientos.'));
        } finally {
            setLoadingMovimientos(false);
        }
    };

    const abrirInventario = (producto) => {
        setInventarioProducto(producto);
        setStockCommand({
            quantity: '', delta: '', movementId: '',
            reason_code: 'MANUAL_D3', note: ''
        });
        cargarMovimientos(producto.id);
    };

    const refrescarInventario = async () => {
        await cargarProductos();
        const token = localStorage.getItem('access_token');
        const detail = await axios.get(
            `http://127.0.0.1:8000/api/gestion/productos/${inventarioProducto.id}/`,
            { headers: { 'Authorization': `Bearer ${token}` } }
        );
        setInventarioProducto(detail.data);
        if (canViewStock) {
            await cargarProductosStockBajo();
            await cargarMovimientos(inventarioProducto.id);
        }
    };

    const guardarCategoria = async (event) => {
        event.preventDefault();
        const token = localStorage.getItem('access_token');
        const config = { headers: { 'Authorization': `Bearer ${token}` } };
        try {
            if (categoriaForm.id) {
                await axios.patch(
                    `http://127.0.0.1:8000/api/gestion/categorias-productos/${categoriaForm.id}/`,
                    categoriaForm,
                    config
                );
            } else {
                await axios.post(
                    'http://127.0.0.1:8000/api/gestion/categorias-productos/',
                    categoriaForm,
                    config
                );
            }
            notify.success('Categoría guardada correctamente.');
            setCategoriaForm({ id: null, nombre: '', descripcion: '', activo: true });
            await cargarCategorias();
        } catch (error) {
            notify.error(domainError(error, 'No se pudo guardar la categoría.'));
        }
    };

    const eliminarCategoria = async (categoria) => {
        const result = await confirmarAccion({
            title: '¿Eliminar categoría?',
            text: categoria.nombre,
            confirmButtonText: 'Sí, eliminar'
        });
        if (!result.isConfirmed) return;
        try {
            const token = localStorage.getItem('access_token');
            await axios.delete(
                `http://127.0.0.1:8000/api/gestion/categorias-productos/${categoria.id}/`,
                { headers: { 'Authorization': `Bearer ${token}` } }
            );
            await cargarCategorias();
            notify.success('Categoría eliminada.');
        } catch (error) {
            notify.error(domainError(error, 'No se pudo eliminar la categoría.'));
        }
    };

    const ejecutarStock = async (operation) => {
        const token = localStorage.getItem('access_token');
        const headers = { 'Authorization': `Bearer ${token}` };
        const common = {
            reason_code: stockCommand.reason_code.trim(),
            note: stockCommand.note.trim(),
            idempotency_key: newIdempotencyKey(operation)
        };
        try {
            if (operation === 'receive') {
                await axios.post(
                    `http://127.0.0.1:8000/api/gestion/productos/${inventarioProducto.id}/stock/receive/`,
                    { ...common, quantity: Number(stockCommand.quantity) },
                    { headers }
                );
            } else if (operation === 'adjust') {
                await axios.post(
                    `http://127.0.0.1:8000/api/gestion/productos/${inventarioProducto.id}/stock/adjust/`,
                    { ...common, delta: Number(stockCommand.delta) },
                    { headers }
                );
            } else {
                await axios.post(
                    `http://127.0.0.1:8000/api/gestion/stock-movements/${stockCommand.movementId}/correct/`,
                    common,
                    { headers }
                );
            }
            notify.success('Operación de inventario aplicada correctamente.');
            await refrescarInventario();
        } catch (error) {
            notify.error(domainError(error, 'No se pudo aplicar la operación de inventario.'));
        }
    };

    const eliminarProducto = async (id, nombre) => {
        const result = await confirmarAccion({
            title: "¿Eliminar producto?",
            text: `Se eliminará "${nombre}"`,
            confirmButtonText: "Sí, eliminar"
        });
        if (!result.isConfirmed) return;

        try {
            const token = localStorage.getItem('access_token');
            await axios.delete(`http://127.0.0.1:8000/api/gestion/productos/${id}/`, {
                headers: { 'Authorization': `Bearer ${token}` }
            });
            notify.success("Producto eliminado.");
            cargarProductos();
            cargarProductosStockBajo();
        } catch (error) {
            const msg = error.response?.data?.error || "No se pudo eliminar.";
            notify.error(`${msg}`);
        }
    };

    const desactivarProducto = async (id, nombre) => {
        const result = await confirmarAccion({
            title: "¿Desactivar producto?",
            text: `Se desactivará "${nombre}" y no aparecerá en el catálogo.`,
            confirmButtonText: "Sí, desactivar"
        });
        if (!result.isConfirmed) return;

        try {
            const token = localStorage.getItem('access_token');
            await axios.post(`http://127.0.0.1:8000/api/gestion/productos/${id}/desactivar/`, {}, {
                headers: { 'Authorization': `Bearer ${token}` }
            });
            notify.success("Producto desactivado.");
            cargarProductos();
            cargarProductosStockBajo();
        } catch (error) {
            const msg = error.response?.data?.error || "No se pudo desactivar.";
            notify.error(`${msg}`);
        }
    };

    // --- RENDERIZADO TABLA PRINCIPAL ---
    const TablaProductos = ({ datos, esAlerta = false }) => (
        <div className="shadow-lg rounded-lg overflow-hidden border" style={{ backgroundColor: 'white', borderColor: '#D5D1CC' }}>
            {datos.length === 0 ? (
                <div className="p-8 text-center" style={{ color: '#ABA89E' }}>
                    {esAlerta ? "No hay productos con stock bajo" : "No hay productos registrados."}
                </div>
            ) : (
                <table className="min-w-full divide-y" style={{ borderColor: '#D5D1CC' }}>
                    <thead style={{ backgroundColor: '#F5F5EB' }}>
                        <tr>
                            <th className="px-6 py-3 text-left text-xs font-bold uppercase" style={{ color: '#817773' }}>SKU</th>
                            <th className="px-6 py-3 text-left text-xs font-bold uppercase" style={{ color: '#817773' }}>Producto</th>
                            <th className="px-6 py-3 text-left text-xs font-bold uppercase" style={{ color: '#817773' }}>Categoría</th>
                            <th className="px-6 py-3 text-left text-xs font-bold uppercase" style={{ color: '#817773' }}>Precio</th>
                            {canViewStock && <th className="px-6 py-3 text-left text-xs font-bold uppercase" style={{ color: '#817773' }}>Inventario</th>}
                            <th className="px-6 py-3 text-left text-xs font-bold uppercase" style={{ color: '#817773' }}>Compatibilidad</th>
                            {!esAlerta && (canEditProduct || canViewStock || canManageStock) && <th className="px-6 py-3 text-right text-xs font-bold uppercase" style={{ color: '#817773' }}>Acciones</th>}
                        </tr>
                    </thead>
                    <tbody style={{ borderColor: '#D5D1CC' }} className="divide-y">
                        {datos.map((prod) => {
                            const stockDisponible = getStockDisponible(prod);
                            const stockMinimo = Number(prod.stock_minimo || 0);

                            return (
                            <tr key={prod.id} style={{ borderColor: '#E3D5CA' }} onMouseEnter={(e) => e.currentTarget.style.backgroundColor = '#F5F5EB'} onMouseLeave={(e) => e.currentTarget.style.backgroundColor = 'white'}>
                                <td className="px-6 py-4 whitespace-nowrap">
                                    <span className="text-xs font-bold" style={{ color: '#8B8682' }}>{prod.sku}</span>
                                </td>
                                <td className="px-6 py-4">
                                    <div className="text-sm font-bold" style={{ color: '#817773' }}>{prod.nombre}</div>
                                    <div className="text-xs" style={{ color: '#8B8682' }}>{prod.marca}</div>
                                </td>
                                <td className="px-6 py-4 whitespace-nowrap">
                                    <span className="px-2 py-1 text-xs rounded-full" style={{ backgroundColor: '#E8EBF5', color: '#3E5B8E' }}>
                                        {prod.categoria_nombre || 'Sin categoría'}
                                    </span>
                                </td>
                                <td className="px-6 py-4 whitespace-nowrap">
                                    <span className="text-sm font-semibold" style={{ color: '#2E7D2E' }}>
                                        ${parseFloat(prod.precio).toLocaleString()}
                                    </span>
                                </td>
                                {canViewStock && (
                                    <td className="px-6 py-4 whitespace-nowrap text-xs" style={{ color: '#5A5451' }}>
                                        <div>Real: <strong>{prod.stock_real}</strong></div>
                                        <div>Comprometido: <strong>{prod.stock_comprometido}</strong></div>
                                        <div style={{ color: stockDisponible <= stockMinimo ? '#C73E3E' : '#2E7D2E' }}>
                                            Disponible: <strong>{stockDisponible}</strong>
                                        </div>
                                    </td>
                                )}
                                <td className="px-6 py-4 whitespace-nowrap">
                                    <span className="text-xs" style={{ color: '#8B8682' }}>
                                        {opcionesCompatibilidad.find(o => o.value === prod.compatibilidad)?.label || prod.compatibilidad}
                                    </span>
                                </td>
                                {!esAlerta && (canEditProduct || canViewStock || canManageStock) && (
                                    <td className="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
                                        {(canViewStock || canManageStock) && <button onClick={() => abrirInventario(prod)} className="font-bold transition mr-4" style={{ color: '#3E5B8E' }}>Inventario</button>}
                                        {canEditProduct && <button onClick={() => abrirModal(prod)} className="font-bold transition mr-4" style={{ color: '#AB9A91' }}>{canManageProducts ? 'Editar' : 'Editar precio'}</button>}
                                        {canManageProducts && <button onClick={() => desactivarProducto(prod.id, prod.nombre)} className="font-bold transition mr-4" style={{ color: '#8B7500' }}>Desactivar</button>}
                                        {canManageProducts && <button onClick={() => eliminarProducto(prod.id, prod.nombre)} disabled={canViewStock && stockDisponible > 0} className="font-bold transition disabled:opacity-50" style={{ color: '#C73E3E' }}>Eliminar</button>}
                                    </td>
                                )}
                            </tr>
                            );
                        })}
                    </tbody>
                </table>
            )}
        </div>
    );

    // --- RENDERIZADO PRINCIPAL ---
    return (
        <div className="min-h-screen" style={{ backgroundColor: '#F5F5EB' }}>
            {/* HEADER */}
            <div className="bg-white shadow-md border-b" style={{ borderColor: '#E8DCC4' }}>
                <div className="max-w-7xl mx-auto p-6">
                    <div className="flex justify-between items-center">
                        <div>
                            <h1 className="text-3xl font-bold" style={{ color: '#817773' }}>Gestión de Productos</h1>
                            <p className="text-xs mt-1 font-medium" style={{ color: '#8B8682' }}>Administra catálogo e inventario</p>
                        </div>
                        <div className="flex gap-2">
                            <button 
                                onClick={() => navigate('/admin-dashboard')} 
                                className="px-4 py-2 rounded-lg font-bold transition" 
                                style={{ backgroundColor: '#E8DCC4', color: '#817773' }}
                                onMouseEnter={(e) => e.target.style.backgroundColor = '#D5BDAF'}
                                onMouseLeave={(e) => e.target.style.backgroundColor = '#E8DCC4'}
                            >
                                Volver
                            </button>
                            {canManageProducts && canManagePrices && <button
                                onClick={() => abrirModal()}
                                className="text-white px-4 py-2 rounded-lg font-bold shadow-md transition"
                                style={{ backgroundColor: '#817773' }}
                                onMouseEnter={(e) => e.target.style.backgroundColor = '#5A5451'}
                                onMouseLeave={(e) => e.target.style.backgroundColor = '#817773'}
                            >
                                + Nuevo Producto
                            </button>}
                        </div>
                    </div>
                </div>
            </div>

            {/* CONTENIDO */}
            <div className="max-w-7xl mx-auto p-6">
                {/* TABS */}
                <div className="mb-6 bg-white rounded-t-lg shadow-md overflow-hidden border" style={{ borderColor: '#E8DCC4' }}>
                    <div className="flex border-b" style={{ borderColor: '#E8DCC4' }}>
                        <button 
                            onClick={() => setTabActiva('catalogo')}
                            className="px-6 py-4 font-semibold whitespace-nowrap transition-all duration-200 border-b-2"
                            style={{ 
                                color: tabActiva === 'catalogo' ? '#fff' : '#8B8682',
                                backgroundColor: tabActiva === 'catalogo' ? '#817773' : 'transparent',
                                borderColor: tabActiva === 'catalogo' ? '#817773' : 'transparent'
                            }}
                            onMouseEnter={(e) => {
                                if (tabActiva !== 'catalogo') {
                                    e.target.style.backgroundColor = '#E8DCC4';
                                    e.target.style.color = '#817773';
                                }
                            }}
                            onMouseLeave={(e) => {
                                if (tabActiva !== 'catalogo') {
                                    e.target.style.backgroundColor = 'transparent';
                                    e.target.style.color = '#8B8682';
                                }
                            }}
                        >
                            Catálogo Completo ({productos.length})
                        </button>
                        {canManageProducts && <button
                            onClick={() => setTabActiva('categorias')}
                            className="px-6 py-4 font-semibold whitespace-nowrap transition-all duration-200 border-b-2"
                            style={{
                                color: tabActiva === 'categorias' ? '#fff' : '#8B8682',
                                backgroundColor: tabActiva === 'categorias' ? '#817773' : 'transparent',
                                borderColor: tabActiva === 'categorias' ? '#817773' : 'transparent'
                            }}
                        >
                            Categorías
                        </button>}
                        {canViewStock && <button
                            onClick={() => setTabActiva('alertas')}
                            className="px-6 py-4 font-semibold whitespace-nowrap transition-all duration-200 border-b-2"
                            style={{ 
                                color: tabActiva === 'alertas' ? '#fff' : '#8B8682',
                                backgroundColor: tabActiva === 'alertas' ? '#817773' : 'transparent',
                                borderColor: tabActiva === 'alertas' ? '#817773' : 'transparent'
                            }}
                            onMouseEnter={(e) => {
                                if (tabActiva !== 'alertas') {
                                    e.target.style.backgroundColor = '#E8DCC4';
                                    e.target.style.color = '#817773';
                                }
                            }}
                            onMouseLeave={(e) => {
                                if (tabActiva !== 'alertas') {
                                    e.target.style.backgroundColor = 'transparent';
                                    e.target.style.color = '#8B8682';
                                }
                            }}
                        >
                            Stock Bajo ({productosStockBajo.length})
                        </button>}
                        {canManagePromotions && <button
                            onClick={() => setTabActiva('combos')}
                            className="px-6 py-4 font-semibold whitespace-nowrap transition-all duration-200 border-b-2"
                            style={{ 
                                color: tabActiva === 'combos' ? '#fff' : '#8B8682',
                                backgroundColor: tabActiva === 'combos' ? '#817773' : 'transparent',
                                borderColor: tabActiva === 'combos' ? '#817773' : 'transparent'
                            }}
                            onMouseEnter={(e) => {
                                if (tabActiva !== 'combos') {
                                    e.target.style.backgroundColor = '#E8DCC4';
                                    e.target.style.color = '#817773';
                                }
                            }}
                            onMouseLeave={(e) => {
                                if (tabActiva !== 'combos') {
                                    e.target.style.backgroundColor = 'transparent';
                                    e.target.style.color = '#8B8682';
                                }
                            }}
                        >
                            Combos
                        </button>}
                    </div>
                </div>

                {/* CONTENIDO TABS */}
                <div className="bg-white rounded-b-lg shadow-md overflow-hidden border" style={{ borderColor: '#E8DCC4' }}>
                    {loading ? (
                        <div className="p-8 text-center" style={{ color: '#8B8682' }}>Cargando productos...</div>
                    ) : (
                        <>
                            {tabActiva === 'catalogo' && <TablaProductos datos={productos} />}
                            {canManageProducts && tabActiva === 'categorias' && (
                                <div className="p-6 grid grid-cols-1 md:grid-cols-2 gap-6">
                                    <form onSubmit={guardarCategoria} className="space-y-3">
                                        <h2 className="text-xl font-bold" style={{ color: '#817773' }}>
                                            {categoriaForm.id ? 'Editar categoría' : 'Nueva categoría'}
                                        </h2>
                                        <input aria-label="Nombre de categoría" required value={categoriaForm.nombre} onChange={(e) => setCategoriaForm({...categoriaForm, nombre: e.target.value})} className="w-full border rounded p-2" placeholder="Nombre" />
                                        <textarea aria-label="Descripción de categoría" value={categoriaForm.descripcion || ''} onChange={(e) => setCategoriaForm({...categoriaForm, descripcion: e.target.value})} className="w-full border rounded p-2" placeholder="Descripción" />
                                        <label className="flex gap-2"><input type="checkbox" checked={categoriaForm.activo} onChange={(e) => setCategoriaForm({...categoriaForm, activo: e.target.checked})} />Activa</label>
                                        <div className="flex gap-2">
                                            <button type="submit" className="px-4 py-2 rounded text-white" style={{ backgroundColor: '#817773' }}>Guardar categoría</button>
                                            {categoriaForm.id && <button type="button" onClick={() => setCategoriaForm({id: null, nombre: '', descripcion: '', activo: true})}>Cancelar</button>}
                                        </div>
                                    </form>
                                    <div className="space-y-2">
                                        {categorias.map((categoria) => (
                                            <div key={categoria.id} className="border rounded p-3 flex justify-between items-center">
                                                <div><strong>{categoria.nombre}</strong><div className="text-xs">{categoria.descripcion}</div></div>
                                                <div className="flex gap-3">
                                                    <button onClick={() => setCategoriaForm({...categoria})} className="font-bold" style={{ color: '#3E5B8E' }}>Editar</button>
                                                    <button onClick={() => eliminarCategoria(categoria)} className="font-bold" style={{ color: '#C73E3E' }}>Eliminar</button>
                                                </div>
                                            </div>
                                        ))}
                                    </div>
                                </div>
                            )}
                            {canViewStock && tabActiva === 'alertas' && (
                                <div>
                                    {productosStockBajo.length > 0 && (
                                        <div className="m-6 p-4 rounded-lg" style={{ backgroundColor: '#FFE8E8', borderLeft: '4px solid #C73E3E' }}>
                                            <p style={{ color: '#8B3E3E' }} className="font-bold">
                                                {productosStockBajo.length} producto(s) con stock bajo necesitan reabastecimiento
                                            </p>
                                        </div>
                                    )}
                                    <TablaProductos datos={productosStockBajo} esAlerta={true} />
                                </div>
                            )}
                            {canManagePromotions && tabActiva === 'combos' && (
                                <div className="p-6 space-y-8">
                                    <div>
                                        <h2 className="text-xl font-bold mb-4" style={{ color: '#817773' }}>Sugerencias Automáticas</h2>
                                        {loadingCombos ? (
                                            <div className="text-center" style={{ color: '#8B8682' }}>Cargando sugerencias...</div>
                                        ) : combosSugeridos.length === 0 ? (
                                            <div className="text-center p-6 rounded-lg" style={{ backgroundColor: '#F5F5EB', color: '#8B8682' }}>
                                                No hay combos sugeridos pendientes.
                                            </div>
                                        ) : (
                                            <div className="space-y-4">
                                                {combosSugeridos.map((combo) => (
                                                    <div key={combo.id} className="border rounded-lg p-4" style={{ borderColor: '#E8DCC4', backgroundColor: '#FFF' }}>
                                                        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                                                            <div>
                                                                <label className="block text-sm font-medium mb-1" style={{ color: '#817773' }}>Nombre</label>
                                                                <input
                                                                    type="text"
                                                                    value={comboEdiciones[combo.id]?.nombre || ''}
                                                                    onChange={(e) => actualizarEdicionCombo(combo.id, 'nombre', e.target.value)}
                                                                    className="w-full border rounded-md p-2"
                                                                    style={{ borderColor: '#D5D1CC' }}
                                                                />
                                                            </div>
                                                            <div className="md:col-span-2">
                                                                <label className="block text-sm font-medium mb-1" style={{ color: '#817773' }}>Descripción</label>
                                                                <input
                                                                    type="text"
                                                                    value={comboEdiciones[combo.id]?.descripcion || ''}
                                                                    onChange={(e) => actualizarEdicionCombo(combo.id, 'descripcion', e.target.value)}
                                                                    className="w-full border rounded-md p-2"
                                                                    style={{ borderColor: '#D5D1CC' }}
                                                                />
                                                            </div>
                                                            <div>
                                                                <label className="block text-sm font-medium mb-1" style={{ color: '#817773' }}>Descuento (%)</label>
                                                                <input
                                                                    type="number"
                                                                    min="1"
                                                                    max="100"
                                                                    value={comboEdiciones[combo.id]?.descuento_porcentaje || 0}
                                                                    onChange={(e) => actualizarEdicionCombo(combo.id, 'descuento_porcentaje', e.target.value)}
                                                                    className="w-full border rounded-md p-2"
                                                                    style={{ borderColor: '#D5D1CC' }}
                                                                />
                                                            </div>
                                                            <div className="md:col-span-2">
                                                                <label className="block text-sm font-medium mb-1" style={{ color: '#817773' }}>Productos</label>
                                                                <div className="text-sm" style={{ color: '#8B8682' }}>
                                                                    {(combo.productos || []).map((prodId) => {
                                                                        const prod = productos.find((p) => p.id === prodId);
                                                                        return prod ? prod.nombre : `ID ${prodId}`;
                                                                    }).join(', ')}
                                                                </div>
                                                            </div>
                                                        </div>
                                                        <div className="flex justify-end gap-3 mt-4">
                                                            <button
                                                                onClick={() => rechazarCombo(combo.id)}
                                                                className="px-4 py-2 rounded-lg font-bold"
                                                                style={{ backgroundColor: '#FFE8E8', color: '#C73E3E' }}
                                                            >
                                                                Rechazar
                                                            </button>
                                                            <button
                                                                onClick={() => publicarCombo(combo.id)}
                                                                className="px-4 py-2 rounded-lg font-bold text-white"
                                                                style={{ backgroundColor: '#817773' }}
                                                            >
                                                                Publicar
                                                            </button>
                                                        </div>
                                                    </div>
                                                ))}
                                            </div>
                                        )}
                                    </div>

                                    <div className="border-t pt-6" style={{ borderColor: '#E8DCC4' }}>
                                        <h2 className="text-xl font-bold mb-4" style={{ color: '#817773' }}>Crear Combo Manual</h2>
                                        <form onSubmit={crearComboManual} className="space-y-4">
                                            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                                <div>
                                                    <label className="block text-sm font-medium mb-1" style={{ color: '#817773' }}>Nombre *</label>
                                                    <input
                                                        type="text"
                                                        value={comboForm.nombre}
                                                        onChange={(e) => setComboForm({ ...comboForm, nombre: e.target.value })}
                                                        className="w-full border rounded-md p-2"
                                                        style={{ borderColor: '#D5D1CC' }}
                                                    />
                                                </div>
                                                <div>
                                                    <label className="block text-sm font-medium mb-1" style={{ color: '#817773' }}>Descuento (%)</label>
                                                    <input
                                                        type="number"
                                                        min="1"
                                                        max="100"
                                                        value={comboForm.descuento_porcentaje}
                                                        onChange={(e) => setComboForm({ ...comboForm, descuento_porcentaje: e.target.value })}
                                                        className="w-full border rounded-md p-2"
                                                        style={{ borderColor: '#D5D1CC' }}
                                                    />
                                                </div>
                                                <div className="md:col-span-2">
                                                    <label className="block text-sm font-medium mb-1" style={{ color: '#817773' }}>Descripción</label>
                                                    <input
                                                        type="text"
                                                        value={comboForm.descripcion}
                                                        onChange={(e) => setComboForm({ ...comboForm, descripcion: e.target.value })}
                                                        className="w-full border rounded-md p-2"
                                                        style={{ borderColor: '#D5D1CC' }}
                                                    />
                                                </div>
                                                <div>
                                                    <label className="block text-sm font-medium mb-1" style={{ color: '#817773' }}>Días de vigencia</label>
                                                    <input
                                                        type="number"
                                                        min="1"
                                                        value={comboForm.dias_vigencia}
                                                        onChange={(e) => setComboForm({ ...comboForm, dias_vigencia: e.target.value })}
                                                        className="w-full border rounded-md p-2"
                                                        style={{ borderColor: '#D5D1CC' }}
                                                    />
                                                </div>
                                            </div>

                                            <div>
                                                <label className="block text-sm font-medium mb-2" style={{ color: '#817773' }}>Productos *</label>
                                                <div className="grid grid-cols-1 md:grid-cols-2 gap-2 max-h-48 overflow-y-auto border rounded-lg p-3" style={{ borderColor: '#E8DCC4' }}>
                                                    {productos.map((prod) => (
                                                        <label key={prod.id} className="flex items-center gap-2 text-sm" style={{ color: '#5A5451' }}>
                                                            <input
                                                                type="checkbox"
                                                                checked={comboForm.productos.includes(prod.id)}
                                                                onChange={() => toggleProductoCombo(prod.id)}
                                                            />
                                                            {prod.nombre}
                                                        </label>
                                                    ))}
                                                </div>
                                            </div>

                                            <div className="flex justify-end">
                                                <button
                                                    type="submit"
                                                    className="px-4 py-2 rounded-lg font-bold text-white"
                                                    style={{ backgroundColor: '#817773' }}
                                                >
                                                    Publicar Combo
                                                </button>
                                            </div>
                                        </form>
                                    </div>
                                </div>
                            )}
                        </>
                    )}
                </div>
            </div>
            {inventarioProducto && (
                <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4 z-50 overflow-y-auto">
                    <div className="rounded-xl shadow-2xl max-w-4xl w-full p-6 my-8" style={{ backgroundColor: 'white', maxHeight: '90vh', overflowY: 'auto' }}>
                        <div className="flex justify-between items-center mb-4">
                            <div>
                                <h2 className="text-xl font-bold" style={{ color: '#817773' }}>Inventario — {inventarioProducto.nombre}</h2>
                                <p className="text-xs" style={{ color: '#8B8682' }}>Los movimientos físicos y los compromisos son conceptos separados.</p>
                            </div>
                            <button onClick={() => setInventarioProducto(null)} aria-label="Cerrar inventario" className="font-bold">✕</button>
                        </div>

                        {canViewStock && (
                            <div className="grid grid-cols-3 gap-3 mb-6">
                                <div className="p-3 rounded" style={{ backgroundColor: '#F5F5EB' }}>Stock real<br/><strong>{inventarioProducto.stock_real}</strong></div>
                                <div className="p-3 rounded" style={{ backgroundColor: '#F5F1E8' }}>Comprometido<br/><strong>{inventarioProducto.stock_comprometido}</strong></div>
                                <div className="p-3 rounded" style={{ backgroundColor: '#E8F5E8' }}>Disponible<br/><strong>{inventarioProducto.stock_disponible}</strong></div>
                            </div>
                        )}

                        {canManageStock && (
                            <div className="border rounded-lg p-4 mb-6" style={{ borderColor: '#E8DCC4' }}>
                                <h3 className="font-bold mb-3" style={{ color: '#817773' }}>Operaciones semánticas D1</h3>
                                <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mb-3">
                                    <input aria-label="Motivo de stock" value={stockCommand.reason_code} onChange={(e) => setStockCommand({...stockCommand, reason_code: e.target.value})} className="border rounded p-2" placeholder="Código de motivo" />
                                    <input aria-label="Nota de stock" value={stockCommand.note} onChange={(e) => setStockCommand({...stockCommand, note: e.target.value})} className="border rounded p-2" placeholder="Nota opcional" />
                                </div>
                                <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                                    <div className="border rounded p-3">
                                        <label className="block text-sm font-bold mb-2">Recepción</label>
                                        <input aria-label="Cantidad recibida" type="number" min="1" value={stockCommand.quantity} onChange={(e) => setStockCommand({...stockCommand, quantity: e.target.value})} className="border rounded p-2 w-full mb-2" />
                                        <button type="button" disabled={!stockCommand.quantity || !stockCommand.reason_code.trim()} onClick={() => ejecutarStock('receive')} className="w-full p-2 rounded text-white disabled:opacity-50" style={{ backgroundColor: '#2E7D2E' }}>Recibir stock</button>
                                    </div>
                                    <div className="border rounded p-3">
                                        <label className="block text-sm font-bold mb-2">Ajuste</label>
                                        <input aria-label="Delta de ajuste" type="number" value={stockCommand.delta} onChange={(e) => setStockCommand({...stockCommand, delta: e.target.value})} className="border rounded p-2 w-full mb-2" />
                                        <button type="button" disabled={!stockCommand.delta || Number(stockCommand.delta) === 0 || !stockCommand.reason_code.trim()} onClick={() => ejecutarStock('adjust')} className="w-full p-2 rounded text-white disabled:opacity-50" style={{ backgroundColor: '#8B7500' }}>Ajustar stock</button>
                                    </div>
                                    <div className="border rounded p-3">
                                        <label className="block text-sm font-bold mb-2">Corrección compensatoria</label>
                                        <input aria-label="ID de movimiento" type="number" min="1" value={stockCommand.movementId} onChange={(e) => setStockCommand({...stockCommand, movementId: e.target.value})} className="border rounded p-2 w-full mb-2" />
                                        <button type="button" disabled={!stockCommand.movementId || !stockCommand.reason_code.trim()} onClick={() => ejecutarStock('correct')} className="w-full p-2 rounded text-white disabled:opacity-50" style={{ backgroundColor: '#C73E3E' }}>Solicitar corrección</button>
                                    </div>
                                </div>
                            </div>
                        )}

                        {canViewStock && (
                            <div>
                                <h3 className="font-bold mb-2" style={{ color: '#817773' }}>Movimientos físicos</h3>
                                {loadingMovimientos ? <p>Cargando movimientos...</p> : movimientos.length === 0 ? <p>No hay movimientos físicos.</p> : (
                                    <div className="overflow-x-auto">
                                        <table className="min-w-full text-sm">
                                            <thead><tr><th className="text-left p-2">ID</th><th className="text-left p-2">Tipo</th><th className="text-left p-2">Delta</th><th className="text-left p-2">Antes → Después</th><th className="text-left p-2">Fecha</th></tr></thead>
                                            <tbody>{movimientos.map((movimiento) => <tr key={movimiento.id} className="border-t"><td className="p-2">{movimiento.id}</td><td className="p-2">{movimiento.tipo}</td><td className="p-2">{movimiento.delta}</td><td className="p-2">{movimiento.stock_before} → {movimiento.stock_after}</td><td className="p-2">{new Date(movimiento.created_at).toLocaleString()}</td></tr>)}</tbody>
                                        </table>
                                    </div>
                                )}
                            </div>
                        )}
                    </div>
                </div>
            )}
            {modalAbierto && (
                <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4 z-50 overflow-y-auto">
                    <div className="rounded-xl shadow-2xl max-w-3xl w-full p-6 animate-fade-in-up my-8" style={{ backgroundColor: 'white', maxHeight: '85vh', display: 'flex', flexDirection: 'column' }}>
                        <h2 className="text-xl font-bold mb-4" style={{ color: '#817773', borderBottom: '2px solid #E3D5CA', paddingBottom: '0.5rem' }}>
                            {modoEdicion ? 'Editar Producto' : 'Nuevo Producto'}
                        </h2>
                        
                        <form onSubmit={guardarProducto} className="space-y-4 overflow-y-auto pr-2 flex-1">
                            {/* Fila 1: SKU y Nombre */}
                            <div className="grid grid-cols-2 gap-4">
                                <div>
                                    <label className="block text-sm font-medium mb-1" style={{ color: '#817773' }}>SKU</label>
                                    <input 
                                        type="text" 
                                        name="sku" 
                                        placeholder={modoEdicion ? "SKU" : "Se genera automaticamente"}
                                        className="mt-1 block w-full border rounded-md shadow-sm p-2 focus:ring-2 outline-none"
                                        style={{ borderColor: '#D5D1CC', '--tw-ring-color': '#AB9A91' }}
                                        value={form.sku}
                                        onChange={handleChange}
                                        readOnly={!modoEdicion}
                                        disabled={!canManageProducts}
                                    />
                                </div>
                                <div>
                                    <label className="block text-sm font-medium mb-1" style={{ color: '#817773' }}>Nombre *</label>
                                    <input 
                                        type="text" 
                                        name="nombre" 
                                        aria-label="Nombre *"
                                        required
                                        placeholder="Ej: Shampoo Nutritivo"
                                        className="mt-1 block w-full border rounded-md shadow-sm p-2 focus:ring-2 outline-none"
                                        style={{ borderColor: '#D5D1CC', '--tw-ring-color': '#AB9A91' }}
                                        value={form.nombre}
                                        onChange={handleChange}
                                        disabled={!canManageProducts}
                                    />
                                </div>
                            </div>

                            {/* Fila 2: Marca y Categoría */}
                            <div className="grid grid-cols-2 gap-4">
                                <div>
                                    <label className="block text-sm font-medium mb-1" style={{ color: '#817773' }}>Marca</label>
                                    <input 
                                        type="text" 
                                        name="marca"
                                        placeholder="Ej: TRESEMMÉ"
                                        className="mt-1 block w-full border rounded-md shadow-sm p-2 focus:ring-2 outline-none"
                                        style={{ borderColor: '#D5D1CC', '--tw-ring-color': '#AB9A91' }}
                                        value={form.marca}
                                        onChange={handleChange}
                                        disabled={!canManageProducts}
                                    />
                                </div>
                                <div>
                                    <label className="block text-sm font-medium mb-1" style={{ color: '#817773' }}>Categoría</label>
                                    <select 
                                        name="categoria"
                                        className="mt-1 block w-full border rounded-md shadow-sm p-2 focus:ring-2 outline-none"
                                        style={{ borderColor: '#D5D1CC', '--tw-ring-color': '#AB9A91' }}
                                        value={form.categoria}
                                        onChange={handleChange}
                                        disabled={!canManageProducts}
                                    >
                                        <option value="">-- Seleccionar --</option>
                                        {categorias.map(cat => (
                                            <option key={cat.id} value={cat.id}>{cat.nombre}</option>
                                        ))}
                                    </select>
                                </div>
                            </div>

                            {/* Descripción */}
                            <div>
                                <label className="block text-sm font-medium mb-1" style={{ color: '#817773' }}>Descripción</label>
                                <textarea 
                                    name="descripcion" 
                                    rows="2"
                                    placeholder="Detalles del producto..."
                                    className="mt-1 block w-full border rounded-md shadow-sm p-2 focus:ring-2 outline-none"
                                    style={{ borderColor: '#D5D1CC', '--tw-ring-color': '#AB9A91' }}
                                    value={form.descripcion}
                                    onChange={handleChange}
                                    disabled={!canManageProducts}
                                />
                            </div>

                            {/* Material y Propósito */}
                            <div className="grid grid-cols-2 gap-4">
                                <div>
                                    <label className="block text-sm font-medium mb-1" style={{ color: '#817773' }}>Material Principal</label>
                                    <select 
                                        name="material_principal"
                                        className="mt-1 block w-full border rounded-md shadow-sm p-2 focus:ring-2 outline-none"
                                        style={{ borderColor: '#D5D1CC', '--tw-ring-color': '#AB9A91' }}
                                        value={form.material_principal || ''}
                                        onChange={handleChange}
                                        disabled={!canManageProducts}
                                    >
                                        <option value="">-- Seleccionar --</option>
                                        {opcionesMaterialPrincipal.map(opt => (
                                            <option key={opt.value} value={opt.value}>{opt.label}</option>
                                        ))}
                                    </select>
                                </div>
                                <div>
                                    <label className="block text-sm font-medium mb-1" style={{ color: '#817773' }}>Propósito de Uso</label>
                                    <select 
                                        name="proposito_uso"
                                        className="mt-1 block w-full border rounded-md shadow-sm p-2 focus:ring-2 outline-none"
                                        style={{ borderColor: '#D5D1CC', '--tw-ring-color': '#AB9A91' }}
                                        value={form.proposito_uso || ''}
                                        onChange={handleChange}
                                        disabled={!canManageProducts}
                                    >
                                        <option value="">-- Seleccionar --</option>
                                        {opcionesPropositoUso.map(opt => (
                                            <option key={opt.value} value={opt.value}>{opt.label}</option>
                                        ))}
                                    </select>
                                </div>
                            </div>

                            {/* Precio editable; inventario es sólo lectura y cambia por commands */}
                            <div className="grid grid-cols-3 gap-4">
                                <div>
                                    <label className="block text-sm font-medium mb-1" style={{ color: '#817773' }}>Precio ($) *</label>
                                    <input 
                                        type="number" 
                                        name="precio" 
                                        aria-label="Precio ($) *"
                                        step="0.01"
                                        required={canManagePrices}
                                        placeholder="0.00"
                                        className="mt-1 block w-full border rounded-md shadow-sm p-2 focus:ring-2 outline-none"
                                        style={{ borderColor: '#D5D1CC', '--tw-ring-color': '#AB9A91' }}
                                        value={form.precio}
                                        onChange={handleChange}
                                        disabled={!canManagePrices}
                                    />
                                </div>
                                <div>
                                    <label className="block text-sm font-medium mb-1" style={{ color: '#817773' }}>Stock Real</label>
                                    <div className="mt-1 block w-full border rounded-md p-2 bg-gray-50" style={{ borderColor: '#D5D1CC', color: '#817773' }}>
                                        {form.stock_real ?? 'Sólo con permiso de stock'}
                                    </div>
                                </div>
                                <div>
                                    <label className="block text-sm font-medium mb-1" style={{ color: '#817773' }}>Stock Mínimo</label>
                                    <div className="mt-1 block w-full border rounded-md p-2 bg-gray-50" style={{ borderColor: '#D5D1CC', color: '#817773' }}>
                                        {form.stock_minimo ?? 'Sólo con permiso de stock'}
                                    </div>
                                </div>
                            </div>

                            {/* Compatibilidad y Estado */}
                            <div className="grid grid-cols-2 gap-4">
                                <div>
                                    <label className="block text-sm font-medium mb-1" style={{ color: '#817773' }}>Compatibilidad</label>
                                    <select 
                                        name="compatibilidad"
                                        className="mt-1 block w-full border rounded-md shadow-sm p-2 focus:ring-2 outline-none"
                                        style={{ borderColor: '#D5D1CC', '--tw-ring-color': '#AB9A91' }}
                                        value={form.compatibilidad}
                                        onChange={handleChange}
                                        disabled={!canManageProducts}
                                    >
                                        {opcionesCompatibilidad.map(opt => (
                                            <option key={opt.value} value={opt.value}>{opt.label}</option>
                                        ))}
                                    </select>
                                </div>
                                <div>
                                    <label className="block text-sm font-medium mb-1" style={{ color: '#817773' }}>Estado</label>
                                    <select 
                                        name="estado_publicacion"
                                        className="mt-1 block w-full border rounded-md shadow-sm p-2 focus:ring-2 outline-none"
                                        style={{ borderColor: '#D5D1CC', '--tw-ring-color': '#AB9A91' }}
                                        value={form.estado_publicacion}
                                        onChange={handleChange}
                                        disabled={!canManageProducts}
                                    >
                                        {opcionesEstadoPublicacion.map(opt => (
                                            <option key={opt.value} value={opt.value}>{opt.label}</option>
                                        ))}
                                    </select>
                                </div>
                            </div>

                            {/* Galería de Imágenes - Consolidada */}
                            {canManageProducts && <div>
                                <label className="block text-sm font-medium mb-2" style={{ color: '#817773' }}>Galería de Imágenes</label>
                                
                                {/* Input para subir/agregar imágenes */}
                                <div className="border-2 border-dashed rounded-lg p-4 text-center cursor-pointer transition mb-4 hover:bg-opacity-75" 
                                    style={{ borderColor: '#D5D1CC', backgroundColor: '#FAFAF7' }}>
                                    <input 
                                        type="file"
                                        accept="image/*"
                                        onChange={handleSubirImagen}
                                        className="hidden"
                                        id="imageInput"
                                        multiple
                                    />
                                    <label htmlFor="imageInput" className="cursor-pointer block">
                                        <p className="text-sm font-medium" style={{ color: '#817773' }}>
                                            📷 Haz clic para agregar imágenes
                                        </p>
                                        <p className="text-xs mt-1" style={{ color: '#ABA89E' }}>
                                            PNG, JPG, GIF (máx 5MB cada una • múltiples permitidas)
                                        </p>
                                    </label>
                                </div>

                                {/* Galería unificada de imágenes (principal + adicionales) */}
                                {((form.imagen_url || form.imagen) || imagenesSubidas.length > 0) && (
                                    <div className="grid grid-cols-2 gap-3">
                                        {/* Mostrar imagen principal si existe */}
                                        {(form.imagen_url || form.imagen) && (
                                            <div className="border rounded-lg overflow-hidden relative group" style={{ borderColor: '#D5D1CC' }}>
                                                {form.imagen instanceof File ? (
                                                    <div className="bg-gray-100 p-3 text-center">
                                                        <p className="text-xs font-semibold" style={{ color: '#817773' }}>
                                                            ✅ Nueva imagen principal
                                                        </p>
                                                        <p className="text-xs mt-1" style={{ color: '#8B8682' }}>
                                                            {form.imagen.name}
                                                        </p>
                                                    </div>
                                                ) : (
                                                    <img 
                                                        src={form.imagen_url} 
                                                        alt="Principal"
                                                        className="w-full h-32 object-cover"
                                                        onError={(e) => {
                                                            e.target.src = 'data:image/svg+xml,%3Csvg xmlns="http://www.w3.org/2000/svg" width="200" height="200"%3E%3Crect fill="%23ddd" width="200" height="200"/%3E%3C/svg%3E';
                                                        }}
                                                    />
                                                )}
                                                <div className="absolute inset-0 bg-black bg-opacity-0 group-hover:bg-opacity-40 transition flex items-center justify-center">
                                                    <button
                                                        type="button"
                                                        onClick={eliminarImagen}
                                                        className="opacity-0 group-hover:opacity-100 px-3 py-1 text-sm text-white bg-red-500 rounded hover:bg-red-600 transition"
                                                        title="Eliminar imagen principal"
                                                    >
                                                        ✕ Eliminar
                                                    </button>
                                                </div>
                                                <div className="px-2 py-1 text-xs font-semibold" style={{ backgroundColor: '#E8DCC4', color: '#817773' }}>
                                                    📌 Principal
                                                </div>
                                            </div>
                                        )}

                                        {/* Mostrar imágenes adicionales */}
                                        {imagenesSubidas.map((img) => (
                                            <div key={img.id} className="border rounded-lg overflow-hidden relative group" style={{ borderColor: '#D5D1CC' }}>
                                                <img 
                                                    src={img.preview || img.url} 
                                                    alt="Galería"
                                                    className="w-full h-32 object-cover"
                                                    onError={(e) => {
                                                        e.target.src = 'data:image/svg+xml,%3Csvg xmlns="http://www.w3.org/2000/svg" width="200" height="200"%3E%3Crect fill="%23ddd" width="200" height="200"/%3E%3C/svg%3E';
                                                    }}
                                                />
                                                <div className="absolute inset-0 bg-black bg-opacity-0 group-hover:bg-opacity-40 transition flex items-center justify-center">
                                                    <button
                                                        type="button"
                                                        onClick={() => eliminarImagenSubida(img.id)}
                                                        className="opacity-0 group-hover:opacity-100 px-3 py-1 text-sm text-white bg-red-500 rounded hover:bg-red-600 transition"
                                                        title={img.esExistente ? 'Eliminar del producto' : 'Quitar de la carga'}
                                                    >
                                                        ✕
                                                    </button>
                                                </div>
                                                <div className="px-2 py-1 text-xs" style={{ backgroundColor: img.esExistente ? '#E8F5E8' : '#FFF3E0', color: img.esExistente ? '#2E7D2E' : '#E65100' }}>
                                                    {img.esExistente ? '✓ Guardada' : '⏳ Nueva'}
                                                </div>
                                            </div>
                                        ))}
                                    </div>
                                )}
                                
                                {!((form.imagen_url || form.imagen) || imagenesSubidas.length > 0) && (
                                    <div className="border rounded-lg p-8 text-center" style={{ borderColor: '#E8DCC4', backgroundColor: '#F5F5EB' }}>
                                        <p style={{ color: '#8B8682' }}>No hay imágenes aún</p>
                                        <p className="text-xs" style={{ color: '#ABA89E' }}>Haz clic en el área superior para agregar imágenes</p>
                                    </div>
                                )}
                            </div>}

                            {/* Checkbox Activo */}
                            <div className="flex items-center">
                                <input 
                                    type="checkbox" 
                                    name="activo"
                                    id="activo"
                                    className="h-4 w-4 rounded"
                                    style={{ accentColor: '#817773' }}
                                    checked={form.activo}
                                    onChange={handleChange}
                                    disabled={!canManageProducts}
                                />
                                <label htmlFor="activo" className="ml-2 text-sm font-medium" style={{ color: '#817773' }}>
                                    Producto activo
                                </label>
                            </div>

                            {/* Botones */}
                            <div className="flex justify-end gap-3 mt-6 pt-4 border-t" style={{ borderColor: '#D5D1CC' }}>
                                <button 
                                    type="button" 
                                    onClick={cerrarModal}
                                    className="px-4 py-2 border rounded-lg font-medium transition"
                                    style={{ borderColor: '#D5BDAF', color: '#817773' }}
                                    onMouseEnter={(e) => e.target.style.backgroundColor = '#F5F5EB'}
                                    onMouseLeave={(e) => e.target.style.backgroundColor = 'transparent'}
                                >
                                    Cancelar
                                </button>
                                <button 
                                    type="submit" 
                                    className="px-4 py-2 text-white rounded-lg font-bold transition"
                                    style={{ backgroundColor: '#817773' }}
                                    onMouseEnter={(e) => e.target.style.backgroundColor = '#5A5451'}
                                    onMouseLeave={(e) => e.target.style.backgroundColor = '#817773'}
                                >
                                    {modoEdicion ? 'Guardar Cambios' : 'Crear Producto'}
                                </button>
                            </div>
                        </form>
                    </div>
                </div>
            )}
        </div>
    );
};

export default GestionProductos;
