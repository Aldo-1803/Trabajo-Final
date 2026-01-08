import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import GenericTableManager from '../../components/admin/GenericTableManager';

const ConfiguracionAdmin = () => {
    const navigate = useNavigate();
    const [tabActivo, setTabActivo] = useState('tipoCabello');

    // Definición de todas las tablas configurables con campos específicos
    const tablas = {
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
        }
    };

    const tabsArray = Object.entries(tablas).map(([key, value]) => ({
        key,
        ...value
    }));

    return (
        <div className="min-h-screen bg-gray-100">
            {/* HEADER */}
            <div className="bg-white shadow-md">
                <div className="max-w-7xl mx-auto px-6 py-6">
                    <div className="flex justify-between items-center">
                        <div>
                            <h1 className="text-3xl font-bold text-gray-800">Configuración del Sistema</h1>
                            <p className="text-gray-500 mt-1">Gestiona los parámetros y catálogos del salón</p>
                        </div>
                        <button
                            onClick={() => navigate('/admin-dashboard')}
                            className="text-gray-500 hover:underline px-4 py-2 border rounded-lg"
                        >
                            ← Volver
                        </button>
                    </div>
                </div>
            </div>

            {/* TABS (PESTAÑAS) */}
            <div className="max-w-7xl mx-auto px-6 py-8">
                <div className="bg-white shadow-md rounded-t-lg">
                    <div className="flex overflow-x-auto border-b">
                        {tabsArray.map((tab) => (
                            <button
                                key={tab.key}
                                onClick={() => setTabActivo(tab.key)}
                                className={`px-6 py-4 font-semibold whitespace-nowrap transition-colors ${
                                    tabActivo === tab.key
                                        ? 'text-blue-600 border-b-2 border-blue-600 bg-blue-50'
                                        : 'text-gray-600 hover:text-gray-900 hover:bg-gray-50'
                                }`}
                            >
                                {tab.nombre}
                            </button>
                        ))}
                    </div>
                </div>

                {/* CONTENIDO DE LAS TABS */}
                <div className="bg-gray-100 py-8">
                    {tabsArray.map((tab) => (
                        <div
                            key={tab.key}
                            style={{ display: tabActivo === tab.key ? 'block' : 'none' }}
                        >
                            <GenericTableManager
                                apiUrl={tab.apiUrl}
                                titulo={tab.nombre}
                                campos={tab.campos}
                            />
                        </div>
                    ))}
                </div>
            </div>
        </div>
    );
};

export default ConfiguracionAdmin;
