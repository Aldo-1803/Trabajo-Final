import React from 'react';
import { Routes, Route, Navigate, useLocation } from 'react-router-dom';
import ProtectedRoute from './ProtectedRoute';
import { AUTH_ROUTES, CLIENTE_ROUTES, ADMIN_ROUTES, NO_HEADER_ROUTES } from './routes';

// Imports - Auth Pages
import Login from '../pages/auth/Login';
import Registro from '../pages/auth/Registro';
import RecuperarContrasena from '../pages/auth/RecuperarContrasena';
import ResetearClave from '../pages/auth/ResetearClave';

// Imports - Cliente Pages
import Perfil from '../pages/cliente/Perfil';
import EditarPerfil from '../pages/cliente/EditarPerfil';
import ReservaCliente from '../pages/cliente/ReservaCliente';
import MisTurnos from '../pages/cliente/MisTurnos';
import MisPedidos from '../pages/cliente/MisPedidos';
import MiAgenda from '../pages/cliente/MiAgenda';
import CatalogoRutinas from '../pages/cliente/CatalogoRutinas';
import CatalogoProductos from '../pages/cliente/CatalogoProductos';
import MisRutinas from '../pages/cliente/MisRutinas';
import DetalleRutina from '../pages/cliente/DetalleRutina';
import CatalogoServicios from '../pages/cliente/CatalogoServicios';
import DetalleServicio from '../pages/cliente/DetalleServicio';
import DetallePromocion from '../pages/cliente/DetallePromocion';
import Carrito from '../pages/cliente/Carrito';
import ContenidoRecomendado from '../pages/cliente/ContenidoRecomendado';
import ContenidoPublico from '../pages/cliente/ContenidoPublico';
import ContenidoGuardado from '../pages/cliente/ContenidoGuardado';
import DetalleContenido from '../pages/cliente/DetalleContenido';

// Imports - Admin Pages
import DashboardAdmin from '../pages/admin/DashboardAdmin';
import Reportes from '../pages/admin/Reportes';
import NuevoTurno from '../pages/admin/NuevoTurno';
import GestionTurnos from '../pages/admin/GestionTurnos';
import GestionarRutinas from '../pages/admin/GestionarRutinas';
import GestionarServicios from '../pages/admin/GestionarServicios';
import GestionarReglas from '../pages/admin/GestionarReglas';
import GestionProductos from '../pages/admin/GestionProductos';
import GestionUsuarios from '../pages/admin/GestionUsuarios';
import GestionClientes from '../pages/admin/GestionClientes';
import GestionEquipamiento from '../pages/admin/GestionEquipamiento';
import GestionPersonal from '../pages/admin/GestionPersonal';
import ConfiguracionAdmin from '../pages/admin/ConfiguracionAdmin';
import AgendaAdmin from '../pages/admin/AgendaAdmin';

// Imports - Admin Pages (Contenido Educativo)
import GestionContenidoEducativo from '../pages/admin/GestionContenidoEducativo';
import EditorContenidoEducativo from '../pages/admin/EditorContenidoEducativo';

// Imports - Admin Pages (Órdenes)
import GestionOrdenes from '../pages/admin/GestionOrdenes';
import HistorialPagos from '../pages/admin/HistorialPagos';

// Imports - Admin Pages (Auditoría)
import Auditoria from '../pages/admin/Auditoria';

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
                <Route path={AUTH_ROUTES.RESETEAR_CLAVE} element={<ResetearClave />} />

                {/* Cliente Routes */}
                <Route path={CLIENTE_ROUTES.PERFIL} element={<ProtectedRoute><Perfil /></ProtectedRoute>} />
                <Route path={CLIENTE_ROUTES.EDITAR_PERFIL} element={<ProtectedRoute><EditarPerfil /></ProtectedRoute>} />
                <Route path={CLIENTE_ROUTES.RESERVAR} element={<ProtectedRoute><ReservaCliente /></ProtectedRoute>} />
                <Route path={CLIENTE_ROUTES.MIS_TURNOS} element={<ProtectedRoute><MisTurnos /></ProtectedRoute>} />
                <Route path={CLIENTE_ROUTES.MIS_PEDIDOS} element={<ProtectedRoute><MisPedidos /></ProtectedRoute>} />
                <Route path={CLIENTE_ROUTES.MI_AGENDA} element={<ProtectedRoute><MiAgenda /></ProtectedRoute>} />
                <Route path={CLIENTE_ROUTES.CATALOGO_RUTINAS} element={<ProtectedRoute><CatalogoRutinas /></ProtectedRoute>} />
                <Route path={CLIENTE_ROUTES.CATALOGO_PRODUCTOS} element={<ProtectedRoute><CatalogoProductos /></ProtectedRoute>} />
                <Route path={CLIENTE_ROUTES.MIS_RUTINAS} element={<ProtectedRoute><MisRutinas /></ProtectedRoute>} />
                <Route path={CLIENTE_ROUTES.RUTINA_DETALLE} element={<ProtectedRoute><DetalleRutina /></ProtectedRoute>} />
                <Route path={CLIENTE_ROUTES.CATALOGO_SERVICIOS} element={<ProtectedRoute><CatalogoServicios /></ProtectedRoute>} />
                <Route path={CLIENTE_ROUTES.SERVICIO_DETALLE} element={<ProtectedRoute><DetalleServicio /></ProtectedRoute>} />
                <Route path={CLIENTE_ROUTES.PROMOCION_DETALLE} element={<ProtectedRoute><DetallePromocion /></ProtectedRoute>} />
                <Route path={CLIENTE_ROUTES.CARRITO} element={<ProtectedRoute><Carrito /></ProtectedRoute>} />
                <Route path={CLIENTE_ROUTES.CONTENIDO_RECOMENDADO} element={<ProtectedRoute><ContenidoRecomendado /></ProtectedRoute>} />
                <Route path={CLIENTE_ROUTES.CONTENIDO_PUBLICO} element={<ProtectedRoute><ContenidoPublico /></ProtectedRoute>} />
                <Route path={CLIENTE_ROUTES.CONTENIDO_GUARDADO} element={<ProtectedRoute><ContenidoGuardado /></ProtectedRoute>} />
                <Route path={CLIENTE_ROUTES.CONTENIDO_DETALLE} element={<ProtectedRoute><DetalleContenido /></ProtectedRoute>} />

                {/* Admin Routes */}
                <Route path={ADMIN_ROUTES.DASHBOARD} element={<ProtectedRoute><DashboardAdmin /></ProtectedRoute>} />
                <Route path={ADMIN_ROUTES.REPORTES} element={<ProtectedRoute><Reportes /></ProtectedRoute>} />
                <Route path={ADMIN_ROUTES.NUEVO_TURNO} element={<ProtectedRoute><NuevoTurno /></ProtectedRoute>} />
                <Route path={ADMIN_ROUTES.TURNOS} element={<ProtectedRoute><GestionTurnos /></ProtectedRoute>} />
                <Route path={ADMIN_ROUTES.GESTIONAR_RUTINAS} element={<ProtectedRoute><GestionarRutinas /></ProtectedRoute>} />
                <Route path={ADMIN_ROUTES.RUTINA_DETALLE} element={<ProtectedRoute><DetalleRutina /></ProtectedRoute>} />
                <Route path={ADMIN_ROUTES.SERVICIOS} element={<ProtectedRoute><GestionarServicios /></ProtectedRoute>} />
                <Route path={ADMIN_ROUTES.REGLAS} element={<ProtectedRoute><GestionarReglas /></ProtectedRoute>} />
                <Route path={ADMIN_ROUTES.PRODUCTOS} element={<ProtectedRoute><GestionProductos /></ProtectedRoute>} />
                <Route path={ADMIN_ROUTES.USUARIOS} element={<ProtectedRoute><GestionUsuarios /></ProtectedRoute>} />
                <Route path={ADMIN_ROUTES.CLIENTES} element={<ProtectedRoute><GestionClientes /></ProtectedRoute>} />
                <Route path={ADMIN_ROUTES.PERSONAL} element={<ProtectedRoute><GestionPersonal /></ProtectedRoute>} />
                <Route path={ADMIN_ROUTES.EQUIPAMIENTO} element={<ProtectedRoute><GestionEquipamiento /></ProtectedRoute>} />
                <Route path={ADMIN_ROUTES.AGENDA} element={<ProtectedRoute><AgendaAdmin /></ProtectedRoute>} />
                <Route path={ADMIN_ROUTES.CONFIGURACION} element={<ProtectedRoute><ConfiguracionAdmin /></ProtectedRoute>} />

                {/* Admin Routes - Contenido Educativo */}
                <Route path={ADMIN_ROUTES.CONTENIDO_EDUCATIVO} element={<ProtectedRoute><GestionContenidoEducativo /></ProtectedRoute>} />
                <Route path={ADMIN_ROUTES.CREAR_CONTENIDO} element={<ProtectedRoute><EditorContenidoEducativo /></ProtectedRoute>} />
                <Route path={ADMIN_ROUTES.EDITAR_CONTENIDO} element={<ProtectedRoute><EditorContenidoEducativo /></ProtectedRoute>} />

                {/* Admin Routes - Órdenes */}
                <Route path={ADMIN_ROUTES.ORDENES} element={<ProtectedRoute><GestionOrdenes /></ProtectedRoute>} />
                <Route path={ADMIN_ROUTES.CAJA} element={<ProtectedRoute><HistorialPagos /></ProtectedRoute>} />

                {/* Admin Routes - Auditoría */}
                <Route path={ADMIN_ROUTES.AUDITORIA} element={<ProtectedRoute><Auditoria /></ProtectedRoute>} />

                {/* Default Route */}
                <Route path="/" element={<Navigate to={AUTH_ROUTES.LOGIN} />} />
            </Routes>
        </>
    );
};

export default AppRoutes;
