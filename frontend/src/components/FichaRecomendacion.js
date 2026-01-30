import React from 'react';

/**
 * FichaRecomendacion
 * 
 * Componente reutilizable que muestra una tarjeta profesional con la recomendación
 * de servicio basada en el diagnóstico capilar.
 * 
 * Props:
 *  - diagnostico: objeto con servicio_urgente_nombre, servicio_urgente_id
 *  - turnoNotificacion: objeto con datos_extra (profesional_id, fecha, hora)
 *  - navigate: función de navegación (useNavigate)
 *  - onAgendar: callback opcional cuando se hace clic en "Agendar Turno"
 */
const FichaRecomendacion = ({ diagnostico, turnoNotificacion, navigate, onAgendar }) => {
    if (!diagnostico?.servicio_urgente_nombre) {
        return null; // No mostrar si no hay servicio urgente
    }

    const handleAgendar = () => {
        const parametos = {
            servicio_id: diagnostico.servicio_urgente_id,
            profesional_id: turnoNotificacion?.datos_extra?.profesional_id || null,
            fecha: turnoNotificacion?.datos_extra?.fecha || null,
            hora: turnoNotificacion?.datos_extra?.hora || null
        };

        if (onAgendar) {
            onAgendar(parametos);
        } else {
            navigate('/reserva', { state: parametos });
        }
    };

    return (
        <div className="mt-6 p-8 rounded-xl border-2 shadow-lg" style={{ borderColor: '#E11D48', backgroundColor: '#FEF2F2' }}>
            {/* Encabezado */}
            <div className="flex items-start gap-4 mb-6">
                <div style={{ color: '#E11D48' }} className="text-4xl flex-shrink-0">⚡</div>
                <div className="flex-1">
                    <p className="text-xs font-bold uppercase tracking-widest" style={{ color: '#E11D48' }}>
                        Recomendación Profesional
                    </p>
                    <h3 className="text-3xl font-bold mt-2" style={{ color: '#817773' }}>
                        {diagnostico.servicio_urgente_nombre}
                    </h3>
                </div>
            </div>

            {/* Descripción */}
            <div className="mb-6 p-4 rounded-lg" style={{ backgroundColor: '#FFFFFF' }}>
                <p style={{ color: '#817773' }} className="text-base leading-relaxed">
                    Basado en tu diagnóstico capilar, nuestro equipo profesional recomienda este servicio 
                    como el más beneficioso para tu tipo y estado de cabello. 
                    Es el momento ideal para actuar y recuperar la salud capilar.
                </p>
            </div>

            {/* Beneficios */}
            <div className="mb-6 grid grid-cols-1 md:grid-cols-3 gap-3">
                <div className="p-3 rounded-lg" style={{ backgroundColor: '#FFFFFF' }}>
                    <p style={{ color: '#E11D48' }} className="text-sm font-bold">✓ Personalizado</p>
                    <p style={{ color: '#817773' }} className="text-xs mt-1">Diseñado para tu cabello</p>
                </div>
                <div className="p-3 rounded-lg" style={{ backgroundColor: '#FFFFFF' }}>
                    <p style={{ color: '#E11D48' }} className="text-sm font-bold">✓ Profesional</p>
                    <p style={{ color: '#817773' }} className="text-xs mt-1">Aplicado por expertos</p>
                </div>
                <div className="p-3 rounded-lg" style={{ backgroundColor: '#FFFFFF' }}>
                    <p style={{ color: '#E11D48' }} className="text-sm font-bold">✓ Resultados</p>
                    <p style={{ color: '#817773' }} className="text-xs mt-1">Visible desde el primer día</p>
                </div>
            </div>

            {/* Botón de Acción */}
            <div className="flex flex-col md:flex-row gap-3">
                <button
                    onClick={handleAgendar}
                    className="flex-1 px-6 py-4 rounded-lg text-white font-bold shadow-md transform hover:scale-105 transition-all flex items-center justify-center gap-2"
                    style={{ backgroundColor: '#E11D48' }}
                    onMouseEnter={(e) => e.target.style.backgroundColor = '#BE0D38'}
                    onMouseLeave={(e) => e.target.style.backgroundColor = '#E11D48'}
                >
                    <span>📅</span> Agendar Turno Sugerido
                </button>
                <button
                    onClick={() => navigate('/catalogo-servicios')}
                    className="flex-1 px-6 py-4 rounded-lg text-gray-700 font-bold shadow-md transform hover:scale-105 transition-all"
                    style={{ backgroundColor: '#E3D5CA' }}
                    onMouseEnter={(e) => e.target.style.backgroundColor = '#D5BDAF'}
                    onMouseLeave={(e) => e.target.style.backgroundColor = '#E3D5CA'}
                >
                    <span>ℹ️</span> Ver más servicios
                </button>
            </div>
        </div>
    );
};

export default FichaRecomendacion;
