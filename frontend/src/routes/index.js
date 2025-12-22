import React from 'react';
import { Routes, Route, Navigate, useLocation } from 'react-router-dom';
import ProtectedRoute from './ProtectedRoute';
import { AUTH_ROUTES, CLIENTE_ROUTES, ADMIN_ROUTES, NO_HEADER_ROUTES } from './routes';

// Imports - Auth Pages
import Login from '../pages/auth/Login';
import Registro from '../pages/auth/Registro';
import RecuperarContrasena from '../pages/auth/RecuperarContrasena';

// Imports - Cliente Pages
import Perfil from '../pages/cliente/Perfil';
import EditarPerfil from '../pages/cliente/EditarPerfil';
import ReservaCliente from '../pages/cliente/ReservaCliente';
import MisTurnos from '../pages/cliente/MisTurnos';
import MiAgenda from '../pages/cliente/MiAgenda';
import CatalogoRutinas from '../pages/cliente/CatalogoRutinas';
import MisRutinas from '../pages/cliente/MisRutinas';
import DetalleRutina from '../pages/cliente/DetalleRutina';
import CatalogoServicios from '../pages/cliente/CatalogoServicios';
import DetalleServicio from '../pages/cliente/DetalleServicio';

// Imports - Admin Pages
import DashboardAdmin from '../pages/admin/DashboardAdmin';
import NuevoTurno from '../pages/admin/NuevoTurno';
import GestionTurnos from '../pages/admin/GestionTurnos';
import GestionarRutinas from '../pages/admin/GestionarRutinas';
import GestionarServicios from '../pages/admin/GestionarServicios';
import GestionarReglas from '../pages/admin/GestionarReglas';
import GestionProductos from '../pages/admin/GestionProductos';
import GestionUsuarios from '../pages/admin/GestionUsuarios';
import GestionClientes from '../pages/admin/GestionClientes';
import GestionEquipamiento from '../pages/admin/GestionEquipamiento';
import AgendaAdmin from '../pages/admin/AgendaAdmin';

// Imports - Components
import Header from '../components/Header';

export const AppRoutes = () => {
    const location = useLocation();
    const showHeader = !NO_HEADER_ROUTES.includes(location.pathname);

    return (
        <>
            {showHeader && <Header />}
            <Routes>
                {/* Auth Routes */}
                <Route path={AUTH_ROUTES.LOGIN} element={<Login />} />
                <Route path={AUTH_ROUTES.REGISTRO} element={<Registro />} />
                <Route path={AUTH_ROUTES.RECUPERAR_CONTRASENA} element={<RecuperarContrasena />} />

                {/* Cliente Routes */}
                <Route path={CLIENTE_ROUTES.PERFIL} element={<ProtectedRoute><Perfil /></ProtectedRoute>} />
                <Route path={CLIENTE_ROUTES.EDITAR_PERFIL} element={<ProtectedRoute><EditarPerfil /></ProtectedRoute>} />
                <Route path={CLIENTE_ROUTES.RESERVAR} element={<ProtectedRoute><ReservaCliente /></ProtectedRoute>} />
                <Route path={CLIENTE_ROUTES.MIS_TURNOS} element={<ProtectedRoute><MisTurnos /></ProtectedRoute>} />
                <Route path={CLIENTE_ROUTES.MI_AGENDA} element={<ProtectedRoute><MiAgenda /></ProtectedRoute>} />
                <Route path={CLIENTE_ROUTES.CATALOGO_RUTINAS} element={<ProtectedRoute><CatalogoRutinas /></ProtectedRoute>} />
                <Route path={CLIENTE_ROUTES.MIS_RUTINAS} element={<ProtectedRoute><MisRutinas /></ProtectedRoute>} />
                <Route path={CLIENTE_ROUTES.RUTINA_DETALLE} element={<ProtectedRoute><DetalleRutina /></ProtectedRoute>} />
                <Route path={CLIENTE_ROUTES.CATALOGO_SERVICIOS} element={<ProtectedRoute><CatalogoServicios /></ProtectedRoute>} />
                <Route path={CLIENTE_ROUTES.SERVICIO_DETALLE} element={<ProtectedRoute><DetalleServicio /></ProtectedRoute>} />

                {/* Admin Routes */}
                <Route path={ADMIN_ROUTES.DASHBOARD} element={<ProtectedRoute><DashboardAdmin /></ProtectedRoute>} />
                <Route path={ADMIN_ROUTES.NUEVO_TURNO} element={<ProtectedRoute><NuevoTurno /></ProtectedRoute>} />
                <Route path={ADMIN_ROUTES.TURNOS} element={<ProtectedRoute><GestionTurnos /></ProtectedRoute>} />
                <Route path={ADMIN_ROUTES.GESTIONAR_RUTINAS} element={<ProtectedRoute><GestionarRutinas /></ProtectedRoute>} />
                <Route path={ADMIN_ROUTES.RUTINA_DETALLE} element={<ProtectedRoute><DetalleRutina /></ProtectedRoute>} />
                <Route path={ADMIN_ROUTES.SERVICIOS} element={<ProtectedRoute><GestionarServicios /></ProtectedRoute>} />
                <Route path={ADMIN_ROUTES.REGLAS} element={<ProtectedRoute><GestionarReglas /></ProtectedRoute>} />
                <Route path={ADMIN_ROUTES.PRODUCTOS} element={<ProtectedRoute><GestionProductos /></ProtectedRoute>} />
                <Route path={ADMIN_ROUTES.USUARIOS} element={<ProtectedRoute><GestionUsuarios /></ProtectedRoute>} />
                <Route path={ADMIN_ROUTES.CLIENTES} element={<ProtectedRoute><GestionClientes /></ProtectedRoute>} />
                <Route path={ADMIN_ROUTES.EQUIPAMIENTO} element={<ProtectedRoute><GestionEquipamiento /></ProtectedRoute>} />
                <Route path={ADMIN_ROUTES.AGENDA} element={<ProtectedRoute><AgendaAdmin /></ProtectedRoute>} />

                {/* Default Route */}
                <Route path="/" element={<Navigate to={AUTH_ROUTES.LOGIN} />} />
            </Routes>
        </>
    );
};

export default AppRoutes;
