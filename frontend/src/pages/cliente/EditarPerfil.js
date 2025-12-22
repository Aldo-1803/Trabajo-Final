import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';

// Componente reutilizable para los <select> (Sin cambios)
const SelectInput = ({ name, value, onChange, options, label, loading }) => (
    <div className="mb-4">
        <label htmlFor={name} className="block text-sm font-medium text-gray-700 mb-1">
            {label}
        </label>
        <select
            id={name}
            name={name}
            value={value}
            onChange={onChange}
            disabled={loading}
            className="w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-rose-500 focus:border-rose-500"
        >
            {loading ? (
                <option>Cargando...</option>
            ) : (
                <>
                    <option value="">Selecciona una opción</option>
                    {options.map((op) => (
                        <option key={op.id} value={op.id}>{op.nombre}</option>
                    ))}
                </>
            )}
        </select>
    </div>
);

const EditarPerfil = () => {
    const navigate = useNavigate();
    
    // --- 1. ESTADO DEL FORMULARIO ---
    const [formData, setFormData] = useState({
        first_name: '',
        last_name: '',
        email: '',
        // IDs de los catálogos
        tipo_cabello: '',
        porosidad: '',
        grosor: '',
        cuero_cabelludo: '',
        estado_general: '',
        // Campos de texto
        productos_actuales: '',
        historial_servicios: [], // <-- Un array de IDs
    });

    // --- 2. ESTADO DE LOS CATÁLOGOS (MODIFICADO) ---
    const [catalogos, setCatalogos] = useState({
        tipos: [],
        porosidades: [],
        grosores: [],
        cueros: [],
        estados: [],
    });
    
    // --- ¡NUEVO ESTADO! ---
    // const [serviciosQuimicos, setServiciosQuimicos] = useState([]);

    // --- 3. ESTADO DE CARGA Y ERRORES ---
    const [loadingCatalogos, setLoadingCatalogos] = useState(true);
    const [loadingPerfil, setLoadingPerfil] = useState(true);
    const [loadingServicios, setLoadingServicios] = useState(true); 
    const [error, setError] = useState('');
    const [successMessage, setSuccessMessage] = useState('');

    // --- 4. HOOK DE EFECTO ---
    useEffect(() => {
        const fetchDatos = async () => {
            try {
                // Reiniciamos estados de carga
                setLoadingCatalogos(true);
                setLoadingServicios(true);
                setLoadingPerfil(true);
                
                // --- A. Cargar los Catálogos (tipos, porosidad, etc.) ---
                const [
                    tiposRes,
                    porosidadesRes,
                    grosoresRes,
                    cuerosRes,
                    estadosRes,
                ] = await Promise.all([
                    axios.get('/api/gestion/tipos-cabello/'),
                    axios.get('/api/gestion/porosidades-cabello/'),
                    axios.get('/api/gestion/grosores-cabello/'),
                    axios.get('/api/gestion/cueros-cabelludos/'),
                    axios.get('/api/gestion/estados-generales/'),
                ]);
                
                // (Usamos .results por la paginación de Django)
                setCatalogos({
                    tipos: tiposRes.data.results,
                    porosidades: porosidadesRes.data.results,
                    grosores: grosoresRes.data.results,
                    cueros: cuerosRes.data.results,
                    estados: estadosRes.data.results,
                });
                setLoadingCatalogos(false);

                // const serviciosRes = await axios.get('/api/gestion/servicios-quimicos/');
                // setServiciosQuimicos(serviciosRes.data.results);
                setLoadingServicios(false);

                const perfilRes = await axios.get('/api/usuarios/perfil/');
                const perfilData = perfilRes.data;

                setFormData({
                    first_name: perfilData.first_name || '',
                    last_name: perfilData.last_name || '',
                    email: perfilData.email || '',
                    tipo_cabello: perfilData.tipo_cabello || '',
                    porosidad: perfilData.porosidad || '',
                    grosor: perfilData.grosor || '',
                    cuero_cabelludo: perfilData.cuero_cabelludo || '',
                    estado_general: perfilData.estado_general || '',
                    productos_actuales: perfilData.productos_actuales || '',
                    historial_servicios: perfilData.historial_servicios || [], 
                });
                setLoadingPerfil(false);

            } catch (err) {
                console.error("Error al cargar datos:", err);
                setError('No se pudieron cargar tus datos. Intenta recargar.');
                setLoadingCatalogos(false);
                setLoadingServicios(false);
                setLoadingPerfil(false);
            }
        };

        fetchDatos();
    }, []); 

    // --- 5. MANEJADORES ---
    const handleChange = (e) => {
        const { name, value } = e.target;
        setFormData((prev) => ({
            ...prev,
            [name]: value,
        }));
    };

    // handleServicioChange function removed as it was not being used

    const handleSubmit = async (e) => {
        e.preventDefault();
        setError('');
        setSuccessMessage('');

        try {
            // El formData ya tiene 'historial_servicios' como un array [1, 5]
            // Axios lo enviará como JSON automáticamente.
            const response = await axios.put('/api/usuarios/perfil/', formData);

            console.log("Respuesta de actualización:", response.data);
            setSuccessMessage('¡Perfil actualizado con éxito!');
            
            setTimeout(() => {
                navigate('/perfil');
            }, 2000);

        } catch (err) {
            console.error("Error al actualizar:", err);
            if (err.response && err.response.data) {
                const erroresBackend = Object.values(err.response.data).join(' ');
                setError(`Error al actualizar: ${erroresBackend}`);
            } else {
                setError('Ocurrió un error inesperado al guardar.');
            }
        }
    };

    // --- 6. RENDERIZADO DEL COMPONENTE ---
    const isLoading = loadingCatalogos || loadingPerfil || loadingServicios;

    return (
        <div className="min-h-screen bg-gray-50 flex items-center justify-center py-12 px-4 sm:px-6 lg:px-8">
            <div className="max-w-2xl w-full space-y-8 bg-white p-10 rounded-xl shadow-lg">
                <div>
                    <h2 className="mt-6 text-center text-3xl font-extrabold text-gray-900">
                        Editar mi Perfil
                    </h2>
                </div>

                {isLoading && <p className="text-center text-gray-600">Cargando tu información...</p>}
                
                {error && <div className="bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded relative" role="alert">{error}</div>}
                {successMessage && <div className="bg-green-100 border border-green-400 text-green-700 px-4 py-3 rounded relative" role="alert">{successMessage}</div>}

                {!isLoading && !error && (
                    <form className="mt-8 space-y-6" onSubmit={handleSubmit}>
                        
                        <h3 className="text-lg font-medium text-gray-800 border-b pb-2">Datos Personales</h3>
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                            <div>
                                <label htmlFor="first_name" className="block text-sm font-medium text-gray-700">Nombre</label>
                                <input id="first_name" name="first_name" type="text" required className="w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm" value={formData.first_name} onChange={handleChange}/>
                            </div>
                            <div>
                                <label htmlFor="last_name" className="block text-sm font-medium text-gray-700">Apellido</label>
                                <input id="last_name" name="last_name" type="text" required className="w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm" value={formData.last_name} onChange={handleChange}/>
                            </div>
                        </div>
                         <div>
                            <label htmlFor="email" className="block text-sm font-medium text-gray-700">Email</label>
                            <input id="email" name="email" type="email" disabled className="w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm bg-gray-100" value={formData.email}/>
                        </div>

                        <h3 className="text-lg font-medium text-gray-800 border-b pb-2 pt-4">Perfil Capilar</h3>

                        <SelectInput name="tipo_cabello" label="Tipo de Cabello (General)" value={formData.tipo_cabello} onChange={handleChange} options={catalogos.tipos} loading={loadingCatalogos}/>
                        <SelectInput name="porosidad" label="Porosidad" value={formData.porosidad} onChange={handleChange} options={catalogos.porosidades} loading={loadingCatalogos}/>
                        <SelectInput name="grosor" label="Grosor" value={formData.grosor} onChange={handleChange} options={catalogos.grosores} loading={loadingCatalogos}/>
                        <SelectInput name="cuero_cabelludo" label="Cuero Cabelludo" value={formData.cuero_cabelludo} onChange={handleChange} options={catalogos.cueros} loading={loadingCatalogos}/>
                        <SelectInput name="estado_general" label="Estado General del Cabello" value={formData.estado_general} onChange={handleChange} options={catalogos.estados} loading={loadingCatalogos}/>

                        <div className="flex gap-4">
                            <button type="button" onClick={() => navigate('/perfil')} className="group relative w-full flex justify-center py-2 px-4 border border-gray-300 rounded-md shadow-sm text-sm font-medium text-gray-700 bg-white hover:bg-gray-50 focus:outline-none">
                                Cancelar
                            </button>
                            <button type="submit" disabled={isLoading} className="group relative w-full flex justify-center py-2 px-4 border border-transparent text-sm font-medium rounded-md text-white bg-rose-500 hover:bg-rose-600 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-rose-500">
                                {isLoading ? 'Guardando...' : 'Guardar Cambios'}
                            </button>
                        </div>
                    </form>
                )}
            </div>
        </div>
    );
};

export default EditarPerfil;