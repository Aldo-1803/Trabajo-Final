import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';
import { confirmarAccion, notify } from '../../utils/notificaciones';

const GestionProductos = () => {
    // --- ESTADOS ---
    const [productos, setProductos] = useState([]);
    const [categorias, setCategorias] = useState([]);
    const [loading, setLoading] = useState(true);
    const [modalAbierto, setModalAbierto] = useState(false);
    const [modoEdicion, setModoEdicion] = useState(false);
    const [tabActiva, setTabActiva] = useState('catalogo'); // 'catalogo' | 'alertas'
    const [productosStockBajo, setProductosStockBajo] = useState([]);
    
    // Estado del Formulario
    const [form, setForm] = useState({
        id: null,
        sku: '',
        nombre: '',
        marca: '',
        categoria: '',
        descripcion: '',
        precio: '',
        stock: '',
        stock_minimo: '',
        imagen_url: '',
        estado_publicacion: 'PUBLICADO',
        compatibilidad: 'TODO',
        activo: true
    });
    
    // Estado para múltiples imágenes
    const [imagenes, setImagenes] = useState([]);
    const [imagenActual, setImagenActual] = useState(0);
    const [cargandoImagen, setCargandoImagen] = useState(false);

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

    const opcionesEstadoPublicacion = [
        { value: 'PUBLICADO', label: 'Publicado' },
        { value: 'BORRADOR', label: 'Borrador' },
        { value: 'DISCONTINUADO', label: 'Discontinuado' },
    ];

    // --- CARGA INICIAL ---
    useEffect(() => {
        cargarProductos();
        cargarCategorias();
        cargarProductosStockBajo();
    }, []);

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

    // --- MANEJADORES DEL FORMULARIO ---
    const handleChange = (e) => {
        const { name, type, checked, value } = e.target;
        setForm({ 
            ...form, 
            [name]: type === 'checkbox' ? checked : value 
        });
    };

    // Manejar carga de imágenes
    const handleSubirImagen = async (e) => {
        const archivos = e.target.files;
        if (!archivos) return;

        const nuevasImagenes = [...imagenes];
        
        for (let archivo of archivos) {
            // Validar que sea imagen
            if (!archivo.type.startsWith('image/')) {
                notify.error('Solo se permiten archivos de imagen');
                continue;
            }

            // Validar tamaño (máx 5MB)
            if (archivo.size > 5 * 1024 * 1024) {
                notify.error(`${archivo.name} es muy grande (máx 5MB)`);
                continue;
            }

            try {
                setCargandoImagen(true);
                
                // Crear FormData para enviar archivo
                const formData = new FormData();
                formData.append('imagen', archivo);

                // Subir al servidor
                const token = localStorage.getItem('access_token');
                const response = await axios.post(
                    'http://127.0.0.1:8000/api/gestion/upload-imagen/',
                    formData,
                    {
                        headers: { 
                            'Authorization': `Bearer ${token}`,
                            'Content-Type': 'multipart/form-data'
                        }
                    }
                );

                console.log('Respuesta upload:', response.data);

                if (response.data && response.data.url) {
                    nuevasImagenes.push(response.data.url);
                    notify.success(`${archivo.name} cargado correctamente`);
                } else {
                    notify.error(`Error: No se recibió URL de imagen para ${archivo.name}`);
                }
            } catch (error) {
                console.error('Error subiendo imagen:', error.response?.data || error.message);
                notify.error(`Error subiendo ${archivo.name}: ${error.response?.data?.error || error.message}`);
            } finally {
                setCargandoImagen(false);
            }
        }

        setImagenes(nuevasImagenes);
        
        // Establecer la primera imagen como principal
        if (nuevasImagenes.length > 0) {
            setForm({ ...form, imagen_url: nuevasImagenes[0] });
            setImagenActual(0);
            console.log('Imágenes seteadas:', nuevasImagenes);
        }
        
        e.target.value = ''; // Reset input
    };

    // Eliminar imagen del carrusel
    const eliminarImagen = (indice) => {
        const nuevasImagenes = imagenes.filter((_, i) => i !== indice);
        setImagenes(nuevasImagenes);
        
        if (nuevasImagenes.length === 0) {
            setForm({ ...form, imagen_url: '' });
            setImagenActual(0);
        } else if (imagenActual >= nuevasImagenes.length) {
            setImagenActual(Math.max(0, nuevasImagenes.length - 1));
            setForm({ ...form, imagen_url: nuevasImagenes[Math.max(0, nuevasImagenes.length - 1)] });
        } else {
            setForm({ ...form, imagen_url: nuevasImagenes[imagenActual] });
        }
    };

    // Cambiar imagen actual en carrusel
    const cambiarImagen = (indice) => {
        setImagenActual(indice);
        setForm({ ...form, imagen_url: imagenes[indice] });
    };

    const abrirModal = (producto = null) => {
        if (producto) {
            setModoEdicion(true);
            setForm(producto);
            // Si hay imagen_url, la convertimos en array
            if (producto.imagen_url) {
                setImagenes([producto.imagen_url]);
                setImagenActual(0);
            } else {
                setImagenes([]);
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
                precio: '',
                stock: '',
                stock_minimo: '',
                imagen_url: '',
                estado_publicacion: 'PUBLICADO',
                compatibilidad: 'TODO',
                activo: true
            });
            setImagenes([]);
            setImagenActual(0);
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
        if (!form.sku || !form.sku.trim()) {
            notify.error("El SKU es requerido.");
            return;
        }

        if (!form.nombre || !form.nombre.trim()) {
            notify.error("El nombre del producto es requerido.");
            return;
        }

        if (!form.precio || parseFloat(form.precio) <= 0) {
            notify.error("El precio debe ser mayor a 0.");
            return;
        }

        if (!form.stock && form.stock !== 0) {
            notify.error("El stock es requerido.");
            return;
        }

        if (!form.categoria || form.categoria === '') {
            notify.error("Por favor selecciona una categoría.");
            return;
        }

        // Validar que haya al menos una imagen
        if (imagenes.length === 0 && !form.imagen_url) {
            notify.error("Por favor agrega al menos una imagen del producto.");
            return;
        }

        // Convertir tipos de datos
        const categoriaId = parseInt(form.categoria);
        if (isNaN(categoriaId)) {
            notify.error("Categoría inválida.");
            return;
        }

        const precioNum = parseFloat(form.precio);
        const stockNum = parseInt(form.stock);
        const stockMinimoNum = parseInt(form.stock_minimo) || 3;

        // Preparar datos para enviar
        const datosProducto = {
            sku: form.sku.trim(),
            nombre: form.nombre.trim(),
            marca: form.marca.trim(),
            categoria: categoriaId,
            descripcion: form.descripcion,
            precio: precioNum,
            stock: stockNum,
            stock_minimo: stockMinimoNum,
            imagen_url: form.imagen_url || (imagenes.length > 0 ? imagenes[0] : ''),
            estado_publicacion: form.estado_publicacion || 'PUBLICADO',
            compatibilidad: form.compatibilidad || 'TODO',
            activo: form.activo === true || form.activo === 'true',
        };

        console.log('Datos a guardar:', datosProducto);

        try {
            let mensaje = "";
            if (modoEdicion) {
                await axios.put(`http://127.0.0.1:8000/api/gestion/productos/${form.id}/`, datosProducto, { headers });
                mensaje = "Producto actualizado correctamente.";
            } else {
                await axios.post('http://127.0.0.1:8000/api/gestion/productos/', datosProducto, { headers });
                mensaje = "Producto creado exitosamente.";
            }
            notify.success(mensaje);
            cerrarModal();
            cargarProductos();
            cargarProductosStockBajo();
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
            
            notify.error(msg);
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
                            <th className="px-6 py-3 text-left text-xs font-bold uppercase" style={{ color: '#817773' }}>Stock</th>
                            <th className="px-6 py-3 text-left text-xs font-bold uppercase" style={{ color: '#817773' }}>Compatibilidad</th>
                            {!esAlerta && <th className="px-6 py-3 text-right text-xs font-bold uppercase" style={{ color: '#817773' }}>Acciones</th>}
                        </tr>
                    </thead>
                    <tbody style={{ borderColor: '#D5D1CC' }} className="divide-y">
                        {datos.map((prod) => (
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
                                <td className="px-6 py-4 whitespace-nowrap">
                                    {prod.stock > prod.stock_minimo ? (
                                        <span className="px-2 py-1 text-xs font-bold rounded-full" style={{ backgroundColor: '#E8F5E8', color: '#2E7D2E' }}>
                                            {prod.stock} u.
                                        </span>
                                    ) : prod.stock > 0 ? (
                                        <span className="px-2 py-1 text-xs font-bold rounded-full animate-pulse" style={{ backgroundColor: '#F5F1E8', color: '#8B7500' }}>
                                            {prod.stock} u.
                                        </span>
                                    ) : (
                                        <span className="px-2 py-1 text-xs font-bold rounded-full" style={{ backgroundColor: '#FFE8E8', color: '#C73E3E' }}>
                                            Sin Stock
                                        </span>
                                    )}
                                </td>
                                <td className="px-6 py-4 whitespace-nowrap">
                                    <span className="text-xs" style={{ color: '#8B8682' }}>
                                        {opcionesCompatibilidad.find(o => o.value === prod.compatibilidad)?.label || prod.compatibilidad}
                                    </span>
                                </td>
                                {!esAlerta && (
                                    <td className="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
                                        <button 
                                            onClick={() => abrirModal(prod)}
                                            className="font-bold transition mr-4"
                                            style={{ color: '#AB9A91' }}
                                            onMouseEnter={(e) => e.target.style.color = '#817773'}
                                            onMouseLeave={(e) => e.target.style.color = '#AB9A91'}
                                        >
                                            Editar
                                        </button>
                                        <button 
                                            onClick={() => eliminarProducto(prod.id, prod.nombre)}
                                            className="font-bold transition"
                                            style={{ color: '#C73E3E' }}
                                            onMouseEnter={(e) => e.target.style.color = '#8B3E3E'}
                                            onMouseLeave={(e) => e.target.style.color = '#C73E3E'}
                                        >
                                            Eliminar
                                        </button>
                                    </td>
                                )}
                            </tr>
                        ))}
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
                            <button 
                                onClick={() => abrirModal()}
                                className="text-white px-4 py-2 rounded-lg font-bold shadow-md transition"
                                style={{ backgroundColor: '#817773' }}
                                onMouseEnter={(e) => e.target.style.backgroundColor = '#5A5451'}
                                onMouseLeave={(e) => e.target.style.backgroundColor = '#817773'}
                            >
                                + Nuevo Producto
                            </button>
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
                        <button 
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
                        </button>
                    </div>
                </div>

                {/* CONTENIDO TABS */}
                <div className="bg-white rounded-b-lg shadow-md overflow-hidden border" style={{ borderColor: '#E8DCC4' }}>
                    {loading ? (
                        <div className="p-8 text-center" style={{ color: '#8B8682' }}>Cargando productos...</div>
                    ) : (
                        <>
                            {tabActiva === 'catalogo' && <TablaProductos datos={productos} />}
                            {tabActiva === 'alertas' && (
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
                        </>
                    )}
                </div>
            </div>
            {modalAbierto && (
                <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4 z-50 overflow-y-auto">
                    <div className="rounded-xl shadow-2xl max-w-2xl w-full p-6 animate-fade-in-up my-8" style={{ backgroundColor: 'white' }}>
                        <h2 className="text-xl font-bold mb-4" style={{ color: '#817773', borderBottom: '2px solid #E3D5CA', paddingBottom: '0.5rem' }}>
                            {modoEdicion ? 'Editar Producto' : 'Nuevo Producto'}
                        </h2>
                        
                        <form onSubmit={guardarProducto} className="space-y-4 max-h-96 overflow-y-auto pr-2">
                            {/* Fila 1: SKU y Nombre */}
                            <div className="grid grid-cols-2 gap-4">
                                <div>
                                    <label className="block text-sm font-medium mb-1" style={{ color: '#817773' }}>SKU *</label>
                                    <input 
                                        type="text" 
                                        name="sku" 
                                        required
                                        placeholder="Ej: PROD-001"
                                        className="mt-1 block w-full border rounded-md shadow-sm p-2 focus:ring-2 outline-none"
                                        style={{ borderColor: '#D5D1CC', '--tw-ring-color': '#AB9A91' }}
                                        value={form.sku}
                                        onChange={handleChange}
                                    />
                                </div>
                                <div>
                                    <label className="block text-sm font-medium mb-1" style={{ color: '#817773' }}>Nombre *</label>
                                    <input 
                                        type="text" 
                                        name="nombre" 
                                        required
                                        placeholder="Ej: Shampoo Nutritivo"
                                        className="mt-1 block w-full border rounded-md shadow-sm p-2 focus:ring-2 outline-none"
                                        style={{ borderColor: '#D5D1CC', '--tw-ring-color': '#AB9A91' }}
                                        value={form.nombre}
                                        onChange={handleChange}
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
                                />
                            </div>

                            {/* Fila 3: Precio y Stock */}
                            <div className="grid grid-cols-3 gap-4">
                                <div>
                                    <label className="block text-sm font-medium mb-1" style={{ color: '#817773' }}>Precio ($) *</label>
                                    <input 
                                        type="number" 
                                        name="precio" 
                                        step="0.01"
                                        required
                                        placeholder="0.00"
                                        className="mt-1 block w-full border rounded-md shadow-sm p-2 focus:ring-2 outline-none"
                                        style={{ borderColor: '#D5D1CC', '--tw-ring-color': '#AB9A91' }}
                                        value={form.precio}
                                        onChange={handleChange}
                                    />
                                </div>
                                <div>
                                    <label className="block text-sm font-medium mb-1" style={{ color: '#817773' }}>Stock *</label>
                                    <input 
                                        type="number" 
                                        name="stock" 
                                        required
                                        placeholder="0"
                                        className="mt-1 block w-full border rounded-md shadow-sm p-2 focus:ring-2 outline-none"
                                        style={{ borderColor: '#D5D1CC', '--tw-ring-color': '#AB9A91' }}
                                        value={form.stock}
                                        onChange={handleChange}
                                    />
                                </div>
                                <div>
                                    <label className="block text-sm font-medium mb-1" style={{ color: '#817773' }}>Stock Mínimo</label>
                                    <input 
                                        type="number" 
                                        name="stock_minimo"
                                        placeholder="5"
                                        className="mt-1 block w-full border rounded-md shadow-sm p-2 focus:ring-2 outline-none"
                                        style={{ borderColor: '#D5D1CC', '--tw-ring-color': '#AB9A91' }}
                                        value={form.stock_minimo}
                                        onChange={handleChange}
                                    />
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
                                    >
                                        {opcionesEstadoPublicacion.map(opt => (
                                            <option key={opt.value} value={opt.value}>{opt.label}</option>
                                        ))}
                                    </select>
                                </div>
                            </div>

                            {/* Galería de Imágenes */}
                            <div>
                                <label className="block text-sm font-medium mb-2" style={{ color: '#817773' }}>Imágenes del Producto</label>
                                
                                {/* Carrusel de imágenes */}
                                {imagenes.length > 0 && (
                                    <div className="mb-4 border rounded-lg p-4" style={{ borderColor: '#E8DCC4', backgroundColor: '#F5F5EB' }}>
                                        <div className="relative w-full flex justify-center items-center mb-4">
                                            <img 
                                                src={imagenes[imagenActual]} 
                                                alt={`Imagen ${imagenActual + 1}`}
                                                className="max-h-64 max-w-full object-contain rounded-lg"
                                                onError={(e) => {
                                                    e.target.src = 'data:image/svg+xml,%3Csvg xmlns="http://www.w3.org/2000/svg" width="200" height="200"%3E%3Crect fill="%23ddd" width="200" height="200"/%3E%3Ctext x="50%25" y="50%25" text-anchor="middle" dy=".3em" fill="%23999"%3EImagen no disponible%3C/text%3E%3C/svg%3E';
                                                }}
                                            />
                                            {imagenes.length > 1 && (
                                                <>
                                                    <button
                                                        type="button"
                                                        onClick={() => cambiarImagen((imagenActual - 1 + imagenes.length) % imagenes.length)}
                                                        className="absolute left-2 bg-white rounded-full p-2 hover:bg-gray-100 transition"
                                                        style={{ color: '#817773' }}
                                                    >
                                                        ❮
                                                    </button>
                                                    <button
                                                        type="button"
                                                        onClick={() => cambiarImagen((imagenActual + 1) % imagenes.length)}
                                                        className="absolute right-2 bg-white rounded-full p-2 hover:bg-gray-100 transition"
                                                        style={{ color: '#817773' }}
                                                    >
                                                        ❯
                                                    </button>
                                                </>
                                            )}
                                        </div>

                                        {/* Miniaturas */}
                                        <div className="flex gap-2 overflow-x-auto pb-2">
                                            {imagenes.map((img, indice) => (
                                                <div key={indice} className="relative flex-shrink-0">
                                                    <img 
                                                        src={img} 
                                                        alt={`Miniatura ${indice + 1}`}
                                                        className={`w-16 h-16 object-cover rounded-lg cursor-pointer border-2 transition ${
                                                            imagenActual === indice ? 'border-green-500' : 'border-gray-300'
                                                        }`}
                                                        onClick={() => cambiarImagen(indice)}
                                                    />
                                                    <button
                                                        type="button"
                                                        onClick={() => eliminarImagen(indice)}
                                                        className="absolute top-0 right-0 bg-red-500 text-white rounded-full w-5 h-5 flex items-center justify-center text-xs font-bold hover:bg-red-600 transition"
                                                    >
                                                        ✕
                                                    </button>
                                                </div>
                                            ))}
                                        </div>

                                        <p className="text-xs mt-2" style={{ color: '#8B8682' }}>
                                            Imagen {imagenActual + 1} de {imagenes.length}
                                        </p>
                                    </div>
                                )}

                                {/* Input para subir imágenes */}
                                <div className="border-2 border-dashed rounded-lg p-4 text-center cursor-pointer transition" 
                                    style={{ borderColor: '#D5D1CC', backgroundColor: cargandoImagen ? '#F5F5EB' : '#FAFAF7' }}>
                                    <input 
                                        type="file"
                                        multiple
                                        accept="image/*"
                                        onChange={handleSubirImagen}
                                        disabled={cargandoImagen}
                                        className="hidden"
                                        id="imageInput"
                                    />
                                    <label htmlFor="imageInput" className="cursor-pointer block">
                                        <p className="text-sm font-medium" style={{ color: '#817773' }}>
                                            {cargandoImagen ? 'Cargando imágenes...' : 'Haz clic para subir imágenes'}
                                        </p>
                                        <p className="text-xs mt-1" style={{ color: '#ABA89E' }}>
                                            PNG, JPG, GIF (máx 5MB cada una)
                                        </p>
                                    </label>
                                </div>

                                {/* O pega URL directa */}
                                <div className="mt-3">
                                    <label className="text-xs font-medium block mb-1" style={{ color: '#817773' }}>O pega URL de imagen:</label>
                                    <input 
                                        type="url" 
                                        placeholder="https://..."
                                        className="w-full border rounded-md p-2 text-sm outline-none focus:ring-2"
                                        style={{ borderColor: '#D5D1CC', '--tw-ring-color': '#AB9A91' }}
                                        onKeyPress={(e) => {
                                            if (e.key === 'Enter' && e.target.value.trim()) {
                                                setImagenes([...imagenes, e.target.value.trim()]);
                                                if (imagenes.length === 0) {
                                                    setForm({ ...form, imagen_url: e.target.value.trim() });
                                                }
                                                e.target.value = '';
                                            }
                                        }}
                                    />
                                    <p className="text-xs mt-1" style={{ color: '#ABA89E' }}>Presiona Enter para agregar</p>
                                </div>
                            </div>

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