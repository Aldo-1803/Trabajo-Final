import React from 'react';
import { notify } from '../../utils/notificaciones';

function Paso1DatosPersonales({ formData, handleChange, nextStep }) {
    
    const handleNext = () => {
        if (formData.email === '' || formData.password === '' || formData.first_name === '') {
            notify.error('Por favor, complete los campos requeridos.');
            return;
        }
        if (formData.password !== formData.password2) {
            notify.error('Las contraseñas no coinciden.');
            return;
        }
        nextStep();
    };

    const campos = [
        { name: 'first_name', label: 'Nombre', type: 'text', required: true },
        { name: 'last_name', label: 'Apellido', type: 'text', required: true },
        { name: 'email', label: 'Correo electrónico', type: 'email', required: true, span: 'md:col-span-2' },
        { name: 'password', label: 'Contraseña', type: 'password', required: true },
        { name: 'password2', label: 'Confirmar Contraseña', type: 'password', required: true },
        { name: 'fecha_nacimiento', label: 'Fecha de Nacimiento', type: 'date', required: false },
        { name: 'zona', label: 'Zona', type: 'text', required: false },
        { name: 'numero', label: 'Teléfono', type: 'text', required: false },
        { name: 'redes', label: 'Red Social (Opcional)', type: 'text', required: false },
        { name: 'sexo', label: 'Sexo', type: 'select', required: false, options: ['Femenino', 'Masculino', 'Otro'], values: ['F', 'M', 'O'] },
    ];

    return (
        <div>
            <h2 className="text-3xl font-bold mb-2 text-rose-900">Tus Datos Personales</h2>
            <p className="text-rose-600 mb-8">Información básica para crear tu perfil</p>
            
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-8">
                {campos.map(campo => (
                    <div key={campo.name} className={campo.span || ''}>
                        <label className="block text-sm font-semibold text-rose-700 mb-3">
                            {campo.label}
                            {campo.required && <span className="text-rose-500">*</span>}
                        </label>
                        
                        {campo.type === 'select' ? (
                            <select 
                                name={campo.name}
                                value={formData[campo.name]}
                                onChange={handleChange}
                                required={campo.required}
                                className="w-full px-4 py-3 border-2 border-rose-200 rounded-lg bg-rose-50 text-gray-700 focus:outline-none focus:ring-2 focus:ring-rose-400 focus:border-transparent transition duration-200 placeholder-gray-400"
                            >
                                <option value="">Selecciona una opción</option>
                                {campo.options && campo.options.map((opt, idx) => (
                                    <option key={idx} value={campo.values[idx]}>
                                        {opt}
                                    </option>
                                ))}
                            </select>
                        ) : (
                            <input 
                                type={campo.type}
                                name={campo.name}
                                value={formData[campo.name]}
                                onChange={handleChange}
                                required={campo.required}
                                className="w-full px-4 py-3 border-2 border-rose-200 rounded-lg bg-rose-50 text-gray-700 focus:outline-none focus:ring-2 focus:ring-rose-400 focus:border-transparent transition duration-200 placeholder-gray-400"
                                placeholder={`Ingresa tu ${campo.label.toLowerCase()}`}
                            />
                        )}
                    </div>
                ))}
            </div>

            <div className="flex justify-end">
                <button 
                    type="button"
                    onClick={handleNext} 
                    className="bg-gradient-to-r from-rose-400 to-orange-400 hover:from-rose-500 hover:to-orange-500 text-white font-bold py-3 px-8 rounded-lg shadow-lg transition duration-200 transform hover:scale-105"
                >
                    Siguiente →
                </button>
            </div>
        </div>
    );
}

export default Paso1DatosPersonales;