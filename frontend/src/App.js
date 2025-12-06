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
import NuevoTurno from './components/admin/NuevoTurno';
import GestionTurnos from './components/admin/GestionTurnos';
import ReservarCliente from './components/ReservaCliente';
import MiAgenda from './components/MiAgenda';
import MisTurnos from './components/MisTurnos';
import DashboardAdmin from './components/admin/DashboardAdmin';
import GestionarRutinas from './components/admin/GestionarRutinas';
import CatalogoRutinas from './components/CatalogoRutinas';
import MisRutinas from './components/MisRutinas';
import GestionarServicios from './components/admin/GestionarServicios';
import GestionarReglas from './components/admin/GestionarReglas';
import DetalleRutina from './components/DetalleRutina';
import GestionProductos from './components/admin/GestionProductos';
import GestionUsuarios from './components/admin/GestionUsuarios';
import GestionClientes from './components/admin/GestionClientes';
import GestionEquipamiento from './components/admin/GestionEquipamiento';

const App = () => {
    return (
        <Routes>
            <Route path="/registro" element={<Registro />} />
            <Route path="/login" element={<Login />} />
            <Route path="/recuperar-contrasena" element={<RecuperarContrasena />} />
            
            {/* Rutas protegidas */}
            <Route path="/perfil" element={<ProtectedRoute> <Perfil /> </ProtectedRoute>} />
            <Route path="/editar-perfil" element={<ProtectedRoute> <EditarPerfil /> </ProtectedRoute>}/>
            <Route path="/admin/nuevo-turno" element={<NuevoTurno />} />
            <Route path="/admin/turnos" element={<ProtectedRoute><GestionTurnos /></ProtectedRoute>} />
            <Route path="/reservar" element={<ProtectedRoute><ReservarCliente /></ProtectedRoute>} />

            <Route path="/mi-agenda" element={<ProtectedRoute><MiAgenda /></ProtectedRoute>} />
            <Route path="/mis-turnos" element={<ProtectedRoute><MisTurnos /></ProtectedRoute>}/>
            <Route path="/admin-dashboard" element={<ProtectedRoute><DashboardAdmin /></ProtectedRoute>}/>
            <Route path="/admin/gestionar-rutinas" element={<ProtectedRoute><GestionarRutinas /></ProtectedRoute>}/>
            <Route path="/catalogo-rutinas" element={<ProtectedRoute><CatalogoRutinas /></ProtectedRoute>}/>
            <Route path="/mis-rutinas" element={<ProtectedRoute><MisRutinas /></ProtectedRoute>}/>
            <Route path="/admin/servicios" element={<ProtectedRoute><GestionarServicios /></ProtectedRoute>} />
            <Route path="/admin/reglas" element={<ProtectedRoute><GestionarReglas /></ProtectedRoute>} />
            <Route path="/admin/rutina/:id" element={<ProtectedRoute><DetalleRutina /></ProtectedRoute>} />
            <Route path="/rutina/:id" element={<ProtectedRoute><DetalleRutina /></ProtectedRoute>} />
            <Route path="/admin/productos" element={<ProtectedRoute><GestionProductos /></ProtectedRoute>} />
            <Route path="/admin/usuarios" element={<ProtectedRoute><GestionUsuarios /></ProtectedRoute>} />
            <Route path="/admin/clientes" element={<ProtectedRoute><GestionClientes /></ProtectedRoute>} />
            <Route path="/admin/equipamiento" element={<ProtectedRoute><GestionEquipamiento /></ProtectedRoute>} />

            {/* Ruta por defecto */}
            <Route path="/" element={<Navigate to="/login" />} />
        </Routes>
    );
};

export default App;
