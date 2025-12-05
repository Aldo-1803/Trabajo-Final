import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { useParams, useNavigate } from 'react-router-dom';
import jsPDF from 'jspdf';

const DetalleRutina = () => {
    const { id } = useParams();
    const navigate = useNavigate();
    const [rutina, setRutina] = useState(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        const fetchRutina = async () => {
            try {
                const token = localStorage.getItem('access_token');
                const response = await axios.get(`http://127.0.0.1:8000/api/gestion/rutinas/${id}/`, {
                    headers: { 'Authorization': `Bearer ${token}` }
                });
                setRutina(response.data);
                setLoading(false);
            } catch (error) {
                console.error(error);
                setLoading(false);
            }
        };
        fetchRutina();
    }, [id]);

    const handleDescargarRutina = (rutina) => {
        const doc = new jsPDF();
        doc.setFontSize(16);
        doc.text(rutina.nombre, 10, 10);
        doc.setFontSize(12);
        doc.text(`Objetivo: ${rutina.objetivo}`, 10, 20);
        doc.text(`Descripción: ${rutina.descripcion}`, 10, 30);

        if (rutina.pasos && rutina.pasos.length > 0) {
            doc.text('Pasos:', 10, 40);
            rutina.pasos.forEach((paso, index) => {
                doc.text(`${index + 1}. ${paso.descripcion}`, 10, 50 + index * 10);
            });
        } else {
            doc.text('Sin pasos definidos.', 10, 40);
        }

        doc.save(`${rutina.nombre}.pdf`);
    };

    const handleAgregarRutina = async () => {
    try {
        // 1. Obtener el token del almacenamiento
        const token = localStorage.getItem('access_token'); 

        if (!token) {
            console.error("No hay token, usuario no logueado");
            // Redirigir a login si es necesario
            return;
        }

        // 2. Asegurarse de enviarlo en los HEADERS
        const response = await axios.post(
            'http://localhost:8000/api/gestion/rutinas/seleccionar/', 
            { rutina_id: rutina.id }, // El body
            {
                headers: {'Authorization': `Bearer ${token}`}
            }
        );

        console.log("Éxito:", response.data);
        alert("¡Rutina agregada a tu perfil!");

    } catch (error) {
        console.error("Error al agregar rutina:", error);
    }
};

    if (loading) return <div className="text-center mt-10">Cargando rutina...</div>;
    if (!rutina) return <div className="text-center mt-10">No se encontró la rutina.</div>;

    return (
        <div className="min-h-screen bg-gray-50 p-6">
            <div className="max-w-3xl mx-auto">
                <button onClick={() => navigate('/perfil')} className="mb-4 text-gray-500 hover:text-gray-800">
                    ← Volver al Perfil
                </button>

                <div className="bg-white rounded-xl shadow-lg overflow-hidden border-t-8 border-pink-500">
                    <div className="p-8">
                        <h1 className="text-3xl font-bold text-gray-800 mb-2">{rutina.nombre}</h1>
                        <p className="text-lg text-pink-600 font-medium mb-4">{rutina.objetivo}</p>
                        <p className="text-gray-600 italic border-l-4 border-gray-200 pl-4 mb-8">
                            {rutina.descripcion}
                        </p>

                        <h3 className="text-xl font-bold text-gray-800 mb-6 border-b pb-2">Pasos de la Rutina</h3>
                        
                        <div className="space-y-6">
                            {rutina.pasos.map((paso, index) => (
                                <div key={index} className="flex gap-4">
                                    <div className="flex-shrink-0">
                                        <div className="w-10 h-10 rounded-full bg-pink-100 text-pink-600 flex items-center justify-center font-bold text-lg">
                                            {index + 1}
                                        </div>
                                    </div>
                                    <div className="bg-gray-50 p-4 rounded-lg flex-1 border border-gray-100">
                                        <h4 className="font-bold text-gray-800 text-lg mb-1">{paso.titulo}</h4>
                                        <p className="text-sm text-pink-500 font-bold uppercase mb-2 text-xs tracking-wider">
                                            Frecuencia: {paso.frecuencia}
                                        </p>
                                        <p className="text-gray-600">{paso.descripcion}</p>
                                    </div>
                                </div>
                            ))}
                        </div>
                    </div>
                    
                    <div className="bg-gray-50 p-6 text-center border-t border-gray-100">
                        <button
                            onClick={() => handleAgregarRutina(rutina.id)}
                            className="bg-pink-500 text-white px-8 py-3 rounded-full font-bold hover:bg-pink-600 shadow-lg transform hover:-translate-y-1 transition-all mb-4"
                        >
                            Agregar a Mis Rutinas
                        </button>
                        <button
                            onClick={() => handleDescargarRutina(rutina)}
                            className="bg-blue-500 text-white px-8 py-3 rounded-full font-bold hover:bg-blue-600 shadow-lg transform hover:-translate-y-1 transition-all"
                        >
                            Descargar PDF
                        </button>
                    </div>
                </div>
            </div>
        </div>
    );
};

export default DetalleRutina;