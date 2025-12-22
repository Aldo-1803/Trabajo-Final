// frontend/src/components/ResetearClave.js (NUEVO ARCHIVO)

import React, { useState } from 'react';
import axios from 'axios';
// Hooks para leer la URL y para navegar
import { useParams, useNavigate } from 'react-router-dom';

const ResetearClave = () => {
    // 1. Obtener el uid y token de la URL
    const { uid, token } = useParams();
    
    // 2. Estados para el formulario
    const [password, setPassword] = useState('');
    const [password2, setPassword2] = useState('');
    const [mensaje, setMensaje] = useState('');
    const [error, setError] = useState('');
    
    const navigate = useNavigate();

    const handleSubmit = async (e) => {
        e.preventDefault();
        setError('');
        setMensaje('');

        // Validación simple en el frontend
        if (password !== password2) {
            setError('Las contraseñas no coinciden.');
            return;
        }

        try {
            // 3. Llamada al Endpoint B que creamos
            const response = await axios.post(
                'http://127.0.0.1:8000/api/usuarios/password-reset/confirm/', 
                {
                    uid: uid,
                    token: token,
                    password: password,
                    password2: password2
                }
            );

            // 4. ¡Éxito!
            setMensaje(response.data.mensaje);
            
            // Redirigir al Login después de 3 segundos
            setTimeout(() => {
                navigate('/login');
            }, 3000);

        } catch (err) {
            console.error('Error al resetear la clave:', err.response.data);
            // Mostrar el error específico del backend (ej. "Token inválido")
            setError(err.response.data.error || 'Error al procesar la solicitud.');
        }
    };

    return (
        <div>
            <h2>Crear Nueva Contraseña</h2>
            
            <form onSubmit={handleSubmit}>
                <div>
                    <label>Nueva Contraseña:</label>
                    <input 
                        type="password" 
                        value={password} 
                        onChange={(e) => setPassword(e.target.value)} 
                        required 
                    />
                </div>
                <div>
                    <label>Confirmar Nueva Contraseña:</label>
                    <input 
                        type="password" 
                        value={password2} 
                        onChange={(e) => setPassword2(e.target.value)} 
                        required 
                    />
                </div>
                <button type="submit">Guardar Contraseña</button>
            </form>

            {mensaje && <p style={{ color: 'green' }}>{mensaje}</p>}
            {error && <p style={{ color: 'red' }}>{error}</p>}
        </div>
    );
};

export default ResetearClave;