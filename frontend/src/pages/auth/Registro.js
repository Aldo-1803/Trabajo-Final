import React, { useState, useEffect } from 'react';
import Paso1DatosPersonales from './Paso1DatosPersonales';
import Paso2PerfilCabello from './Paso2PerfilCabello';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';

const Registro = () => {
    const [step, setStep] = useState(1);
    const [loading, setLoading] = useState(false);
    const [loadingOpciones, setLoadingOpciones] = useState(true);
    const [errorOpciones, setErrorOpciones] = useState('');
    const navigate = useNavigate();

    const [formData, setFormData] = useState({
        email: '',
        password: '',
        password2: '',
        first_name: '',
        last_name: '',
        fecha_nacimiento: '',
        zona: '',
        numero: '',
        redes: '',
        sexo: 'F',
        tipo_cabello: '',
        grosor_cabello: '',
        porosidad_cabello: '',
        cuero_cabelludo: '',
        estado_general: '',
    });

    const [opciones, setOpciones] = useState({
        tipo_cabello: [],
        grosor_cabello: [],
        porosidad_cabello: [],
        cuero_cabelludo: [],
        estado_general: [],
    });

    useEffect(() => {
        const fetchOpciones = async () => {
            try {
                setLoadingOpciones(true);
                setErrorOpciones('');

                const [tipoCabello, grosorCabello, porosidadCabello, cueroCabelludo, estadoGeneral] = 
                    await Promise.all([
                        axios.get('/api/gestion/tipos-cabello/'),
                        axios.get('/api/gestion/grosores-cabello/'),
                        axios.get('/api/gestion/porosidades-cabello/'),
                        axios.get('/api/gestion/cueros-cabelludos/'),
                        axios.get('/api/gestion/estados-generales/'),
                    ]);

                setOpciones({
                    tipo_cabello: tipoCabello.data.results || [],
                    grosor_cabello: grosorCabello.data.results || [],
                    porosidad_cabello: porosidadCabello.data.results || [],
                    cuero_cabelludo: cueroCabelludo.data.results || [],
                    estado_general: estadoGeneral.data.results || [],
                });
            } catch (error) {
                console.error('Error al cargar las opciones:', error);
                setErrorOpciones('Error al cargar las opciones del cabello. Por favor, recarga la página.');
            } finally {
                setLoadingOpciones(false);
            }
        };

        fetchOpciones();
    }, []);

    const handleChange = (e) => {
        const { name, value } = e.target;
        setFormData(prevState => ({
            ...prevState,
            [name]: value,
        }));
    };

    const handleSubmit = async (e) => {
        e.preventDefault();
        setLoading(true);

        try {
            await axios.post('/api/usuarios/registro/', formData);
            alert('¡Registro exitoso! Ahora inicia sesión.');
            navigate('/login');
        } catch (error) {
            console.error('Error al registrar usuario:', error.response?.data);
            if (error.response?.data) {
                const errors = Object.entries(error.response.data);
                const errorMsg = errors.map(([key, value]) => `${key}: ${Array.isArray(value) ? value.join(', ') : value}`).join('\n');
                alert(`Error al registrar:\n${errorMsg}`);
            } else {
                alert('Error al registrar usuario. Intenta nuevamente.');
            }
        } finally {
            setLoading(false);
        }
    };

    const nextStep = () => setStep(prev => prev + 1);
    const prevStep = () => setStep(prev => prev - 1);

    if (loadingOpciones) {
        return (
            <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-rose-50 via-amber-50 to-orange-50">
                <div className="text-center">
                    <div className="inline-block animate-spin rounded-full h-12 w-12 border-4 border-rose-200 border-t-rose-400"></div>
                    <p className="mt-4 text-rose-600 font-medium">Cargando formulario...</p>
                </div>
            </div>
        );
    }

    return (
        <div className="min-h-screen bg-gradient-to-br from-rose-50 via-amber-50 to-orange-50 p-4 flex items-center justify-center">
            <div className="bg-white rounded-2xl shadow-2xl overflow-hidden w-full max-w-3xl">

                {/* Header con gradiente pastel */}
                <div className="bg-gradient-to-r from-rose-300 via-amber-200 to-orange-200 px-6 sm:px-8 py-10">
                    <h1 className="text-4xl font-bold text-rose-900">Crea tu cuenta</h1>
                    <p className="text-rose-700 mt-2 text-lg">Únete a la comunidad Bohemia Hair</p>
                </div>

                {/* Indicador de Progreso */}
                <div className="px-6 sm:px-8 py-6 bg-gradient-to-r from-rose-50 to-orange-50">
                    <div className="flex items-center justify-between mb-3">
                        <p className="text-sm font-semibold text-rose-700">Paso {step} de 2</p>
                        <span className="text-xs text-amber-600 font-medium">
                            {step === 1 ? 'Datos Personales' : 'Perfil de Cabello'}
                        </span>
                    </div>
                    <div className="w-full bg-rose-100 rounded-full h-3">
                        <div 
                            className="bg-gradient-to-r from-rose-400 to-orange-400 h-3 rounded-full transition-all duration-300 shadow-md"
                            style={{ width: step === 1 ? '50%' : '100%' }}
                        ></div>
                    </div>
                </div>

                {/* Error de Opciones */}
                {errorOpciones && (
                    <div className="mx-6 mt-6 p-4 bg-red-50 border-l-4 border-red-400 rounded-lg">
                        <p className="text-red-700 font-medium">{errorOpciones}</p>
                    </div>
                )}

                {/* Contenido del formulario */}
                <form onSubmit={handleSubmit} className="px-6 sm:px-8 py-8">
                    {step === 1 ? (
                        <Paso1DatosPersonales 
                            formData={formData} 
                            handleChange={handleChange} 
                            nextStep={nextStep}
                        />
                    ) : (
                        <Paso2PerfilCabello 
                            formData={formData} 
                            opciones={opciones} 
                            handleChange={handleChange} 
                            prevStep={prevStep} 
                            handleSubmit={handleSubmit}
                            loading={loading}
                        />
                    )}
                </form>

                {/* Footer */}
                <div className="px-6 sm:px-8 py-6 bg-gradient-to-r from-rose-50 to-orange-50 border-t border-rose-100">
                    <div className="space-y-3 text-center text-sm">
                        <p className="text-gray-600">
                            ¿Ya tienes cuenta?{' '}
                            <button 
                                type="button" 
                                onClick={() => navigate('/login')}
                                className="text-rose-600 hover:text-rose-700 font-semibold hover:underline"
                            >
                                Inicia sesión aquí
                            </button>
                        </p>
                        <p className="text-gray-600">
                            ¿Olvidaste tu contraseña?{' '}
                            <button 
                                type="button" 
                                onClick={() => navigate('/recuperar-contrasena')}
                                className="text-amber-600 hover:text-amber-700 font-semibold hover:underline"
                            >
                                Recupérala aquí
                            </button>
                        </p>
                    </div>
                </div>
            </div>
        </div>
    );
};

export default Registro;