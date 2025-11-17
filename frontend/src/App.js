import React from 'react';
// ¡Aquí ya no se importa BrowserRouter!
import { Routes, Route, Navigate } from 'react-router-dom'; 

// Todas las importaciones de componentes van aquí
import Registro from './components/Registro';
import Login from './components/Login';
import RecuperarContrasena from './components/RecuperarContrasena';
import Perfil from './components/Perfil';
import ProtectedRoute from './components/ProtectedRoute';
import EditarPerfil from './components/EditarPerfil';

const App = () => {
    return (
        <Routes>
            <Route path="/registro" element={<Registro />} />
            <Route path="/login" element={<Login />} />
            <Route path="/recuperar-contrasena" element={<RecuperarContrasena />} />
            
            {/* Rutas protegidas */}
            <Route 
                path="/perfil" 
                element={
                    <ProtectedRoute>
                        <Perfil />
                    </ProtectedRoute>
                } 
            />
            <Route 
                path="/editar-perfil" 
                element={
                    <ProtectedRoute>
                        <EditarPerfil />
                    </ProtectedRoute>
                } 
            />
            
            {/* Ruta por defecto */}
            <Route path="/" element={<Navigate to="/login" />} />
        </Routes>
    );
};

export default App;
