// src/components/auth/Paso2PerfilCabello.js
import React, { useState } from 'react';

// Componente de Ayuda Reutilizable (Tooltip)
const InfoTooltip = ({ texto }) => {
    const [visible, setVisible] = useState(false);
    return (
        <div className="relative inline-block ml-2">
            <span 
                onMouseEnter={() => setVisible(true)}
                onMouseLeave={() => setVisible(false)}
                className="cursor-pointer text-rose-500 font-bold hover:text-rose-700 text-lg"
            >
                ℹ️
            </span>
            {visible && (
                <div className="absolute z-10 w-56 p-3 mt-2 text-sm text-white bg-rose-600 rounded-lg shadow-xl">
                    {texto}
                </div>
            )}
        </div>
    );
};

function Paso2PerfilCabello({ formData, opciones, handleChange, prevStep, handleSubmit, loading }) {
    
    const camposCabello = [
        { 
            name: 'tipo_cabello', 
            label: 'Tipo de Cabello', 
            options: opciones.tipo_cabello || [], 
            info: '✨ Ej: Lacio, Ondulado, Rizado, Afro. Define la textura natural de tu cabello.' 
        },
        { 
            name: 'grosor_cabello', 
            label: 'Grosor del Cabello', 
            options: opciones.grosor_cabello || [], 
            info: '📏 Ej: Fino, Medio, Grueso. Determina el diámetro de cada hebra.' 
        },
        { 
            name: 'porosidad_cabello', 
            label: 'Porosidad', 
            options: opciones.porosidad_cabello || [], 
            info: '💧 Baja (repele), Media (normal), Alta (absorbe rápido). Capacidad de absorber humedad.' 
        },
        { 
            name: 'cuero_cabelludo', 
            label: 'Cuero Cabelludo', 
            options: opciones.cuero_cabelludo || [], 
            info: '🧴 Ej: Seco, Normal, Graso. Refleja el estado de tu raíz.' 
        },
        { 
            name: 'estado_general', 
            label: 'Estado General del Cabello', 
            options: opciones.estado_general || [], 
            info: '💇 Cómo se siente tu cabello. Ej: Saludable, Seco, Muy Seco, Dañado.' 
        },
    ];

    return (
        <div>
            <h2 className="text-3xl font-bold mb-2 text-rose-900">Tu Perfil de Cabello</h2>
            <p className="text-rose-600 mb-8">
                Esta información es clave para crear rutinas personalizadas. 
                <span className="text-amber-600 font-medium"> Pasa el cursor sobre los íconos ℹ️ para más información.</span>
            </p>
            
            <div className="grid grid-cols-1 gap-6 mb-8">
                {camposCabello.map(campo => (
                    <div key={campo.name} className="bg-gradient-to-r from-rose-50 to-amber-50 p-6 rounded-xl border-2 border-rose-200 hover:border-rose-300 transition duration-200">
                        <label className="block text-lg font-semibold text-rose-900 mb-3 flex items-center">
                            {campo.label}
                            <InfoTooltip texto={campo.info} />
                        </label>
                        <select 
                            name={campo.name}
                            value={formData[campo.name]}
                            onChange={handleChange}
                            required
                            className="w-full px-4 py-3 border-2 border-rose-200 rounded-lg bg-white text-gray-700 focus:outline-none focus:ring-2 focus:ring-rose-400 focus:border-transparent transition duration-200 font-medium cursor-pointer hover:border-rose-300"
                        >
                            <option value="">Selecciona una opción</option>
                            {Array.isArray(campo.options) && campo.options.length > 0 ? (
                                campo.options.map(op => (
                                    <option key={op.id} value={op.id}>
                                        {op.nombre}
                                    </option>
                                ))
                            ) : (
                                <option disabled>No hay opciones disponibles</option>
                            )}
                        </select>
                    </div>
                ))}
            </div>

            {/* Botones de Navegación */}
            <div className="flex gap-4">
                <button 
                    type="button"
                    onClick={prevStep} 
                    className="flex-1 bg-gray-300 hover:bg-gray-400 text-gray-800 font-bold py-3 px-6 rounded-lg shadow-md transition duration-200 transform hover:scale-105"
                >
                    ← Anterior
                </button>
                <button 
                    type="submit"
                    disabled={loading}
                    className={`flex-1 font-bold py-3 px-6 rounded-lg shadow-lg transition duration-200 transform ${
                        loading 
                            ? 'bg-rose-300 text-gray-500 cursor-not-allowed opacity-50' 
                            : 'bg-gradient-to-r from-rose-400 to-orange-400 hover:from-rose-500 hover:to-orange-500 text-white hover:scale-105'
                    }`}
                >
                    {loading ? 'Registrando...' : '✓ Finalizar Registro'}
                </button>
            </div>
        </div>
    );
}

export default Paso2PerfilCabello;