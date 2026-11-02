import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import GenericTableManager from '../../components/admin/GenericTableManager';
import ConfiguracionGeneral from './ConfiguracionGeneral';

const ConfiguracionAdmin = () => {
    const navigate = useNavigate();
    const [tabActivo, setTabActivo] = useState('configuracionGeneral');

    // Definición de todas las tablas configurables con campos específicos
    const tablas = {
        configuracionGeneral: {
            nombre: 'Configuración General',
            component: <ConfiguracionGeneral />,
            es_component: true
        },
        tipoCabello: {
            nombre: 'Tipos de Cabello',
            apiUrl: '/api/gestion/tipos-cabello/',
            campos: [
                { nombre: 'id', label: 'ID', tipo: 'hidden' },
                { nombre: 'nombre', label: 'Nombre', tipo: 'text' },
                { nombre: 'descripcion', label: 'Descripción', tipo: 'textarea' },
                { nombre: 'activo', label: 'Activo', tipo: 'boolean' },
                { nombre: 'puntaje_base', label: 'Puntaje', tipo: 'number' }
            ]
        },
        grosorCabello: {
            nombre: 'Grosores de Cabello',
            apiUrl: '/api/gestion/grosores-cabello/',
            campos: [
                { nombre: 'id', label: 'ID', tipo: 'hidden' },
                { nombre: 'nombre', label: 'Nombre', tipo: 'text' },
                { nombre: 'descripcion', label: 'Descripción', tipo: 'textarea' },
                { nombre: 'activo', label: 'Activo', tipo: 'boolean' },
                { nombre: 'puntaje_base', label: 'Puntaje', tipo: 'number' }
            ]
        },
        porosidadCabello: {
            nombre: 'Porosidades de Cabello',
            apiUrl: '/api/gestion/porosidades-cabello/',
            campos: [
                { nombre: 'id', label: 'ID', tipo: 'hidden' },
                { nombre: 'nombre', label: 'Nombre', tipo: 'text' },
                { nombre: 'descripcion', label: 'Descripción', tipo: 'textarea' },
                { nombre: 'activo', label: 'Activo', tipo: 'boolean' },
                { nombre: 'puntaje_base', label: 'Puntaje', tipo: 'number' }
            ]
        },
        cueroCabelludo: {
            nombre: 'Tipos de Cuero Cabelludo',
            apiUrl: '/api/gestion/cueros-cabelludos/',
            campos: [
                { nombre: 'id', label: 'ID', tipo: 'hidden' },
                { nombre: 'nombre', label: 'Nombre', tipo: 'text' },
                { nombre: 'descripcion', label: 'Descripción', tipo: 'textarea' },
                { nombre: 'activo', label: 'Activo', tipo: 'boolean' },
                { nombre: 'puntaje_base', label: 'Puntaje', tipo: 'number' }
            ]
        },
        estadoGeneral: {
            nombre: 'Estados Generales',
            apiUrl: '/api/gestion/estados-generales/',
            campos: [
                { nombre: 'id', label: 'ID', tipo: 'hidden' },
                { nombre: 'nombre', label: 'Nombre', tipo: 'text' },
                { nombre: 'descripcion', label: 'Descripción', tipo: 'textarea' },
                { nombre: 'activo', label: 'Activo', tipo: 'boolean' },
                { nombre: 'puntaje_base', label: 'Puntaje', tipo: 'number' }
            ]
        },
        categoriaServicio: {
            nombre: 'Categorías de Servicios',
            apiUrl: '/api/gestion/categorias-servicio/',
            campos: [
                { nombre: 'id', label: 'ID', tipo: 'hidden' },
                { nombre: 'nombre', label: 'Nombre', tipo: 'text' },
                { nombre: 'descripcion', label: 'Descripción', tipo: 'textarea' },
                { nombre: 'activo', label: 'Activo', tipo: 'boolean' }
            ]
        },
        tipoEquipamiento: {
            nombre: 'Tipos de Equipamiento',
            apiUrl: '/api/gestion/tipo-equipamiento/',
            campos: [
                { nombre: 'id', label: 'ID', tipo: 'hidden' },
                { nombre: 'nombre', label: 'Nombre', tipo: 'text' },
                { nombre: 'descripcion', label: 'Descripción', tipo: 'textarea' }
            ]
        },
        categoriaProducto: {
            nombre: 'Categorías de Productos',
            apiUrl: '/api/gestion/categorias-productos/',
            campos: [
                { nombre: 'id', label: 'ID', tipo: 'hidden' },
                { nombre: 'nombre', label: 'Nombre', tipo: 'text' },
                { nombre: 'descripcion', label: 'Descripción', tipo: 'textarea' },
                { nombre: 'activo', label: 'Activo', tipo: 'boolean' }
            ]
        }
    };

    const tabsArray = Object.entries(tablas).map(([key, value]) => ({
        key,
        ...value
    }));

    return (
        <div className="min-h-screen" style={{ backgroundColor: '#F5F5EB' }}>
            {/* HEADER CON TÍTULO */}
            <div className="bg-white shadow-md border-b" style={{ borderColor: '#E8DCC4' }}>
                <div className="max-w-7xl mx-auto px-6 py-6">
                    <div className="flex justify-between items-center">
                        <div>
                            <h1 className="text-3xl font-bold" style={{ color: '#817773' }}>Configuración del Sistema</h1>
                            <p className="text-xs mt-1 font-medium" style={{ color: '#8B8682' }}>Gestiona parámetros y catálogos</p>
                        </div>
                        <button
                            onClick={() => navigate('/admin-dashboard')}
                            className="px-4 py-2 rounded-lg font-bold transition-all duration-200"
                            style={{ backgroundColor: '#E8DCC4', color: '#817773' }}
                            onMouseEnter={(e) => e.target.style.backgroundColor = '#D5BDAF'}
                            onMouseLeave={(e) => e.target.style.backgroundColor = '#E8DCC4'}
                        >
                            Volver
                        </button>
                    </div>
                </div>
            </div>

            {/* TABS (PESTAÑAS) */}
            <div className="max-w-7xl mx-auto px-6 py-8">
                <div className="bg-white shadow-md rounded-lg overflow-hidden border" style={{ borderColor: '#E8DCC4' }}>
                    <div className="flex overflow-x-auto" style={{ borderBottom: '2px solid #E8DCC4' }}>
                        {tabsArray.map((tab) => (
                            <button
                                key={tab.key}
                                onClick={() => setTabActivo(tab.key)}
                                className="px-6 py-4 font-semibold whitespace-nowrap transition-all duration-200 border-b-2 hover:shadow-md"
                                style={{
                                    color: tabActivo === tab.key ? '#fff' : '#8B8682',
                                    borderBottomColor: tabActivo === tab.key ? '#817773' : 'transparent',
                                    backgroundColor: tabActivo === tab.key ? '#817773' : 'transparent'
                                }}
                                onMouseEnter={(e) => {
                                    if (tabActivo !== tab.key) {
                                        e.target.style.backgroundColor = '#E8DCC4';
                                        e.target.style.color = '#817773';
                                    }
                                }}
                                onMouseLeave={(e) => {
                                    if (tabActivo !== tab.key) {
                                        e.target.style.backgroundColor = 'transparent';
                                        e.target.style.color = '#8B8682';
                                    }
                                }}
                            >
                                {tab.nombre}
                            </button>
                        ))}
                    </div>
                </div>

                {/* CONTENIDO DE LAS TABS */}
                <div className="py-8 px-6 bg-white" style={{ backgroundColor: '#fff' }}>
                    {tabsArray.map((tab) => (
                        <div
                            key={tab.key}
                            style={{ display: tabActivo === tab.key ? 'block' : 'none' }}
                        >
                            {tab.es_component ? (
                                tab.component
                            ) : (
                                <GenericTableManager
                                    apiUrl={tab.apiUrl}
                                    titulo={tab.nombre}
                                    campos={tab.campos}
                                />
                            )}
                        </div>
                    ))}
                </div>
            </div>
        </div>
    );
};

export default ConfiguracionAdmin;
