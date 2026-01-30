import React, { useState, useEffect } from 'react';
import { Link, useNavigate, useLocation } from 'react-router-dom';
import axios from 'axios';
import { CLIENTE_ROUTES, ADMIN_ROUTES, AUTH_ROUTES } from '../routes/routes';
import CampanaNotificaciones from './CampanaNotificaciones';

const Header = () => {
    const [user, setUser] = useState(null);
    const [dropdownOpen, setDropdownOpen] = useState(false);
    const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
    const navigate = useNavigate();
    const location = useLocation();

    // Cargar usuario al montar
    useEffect(() => {
        const fetchUser = async () => {
            const token = localStorage.getItem('access_token');
            if (token) {
                try {
                    const response = await axios.get('http://127.0.0.1:8000/api/usuarios/perfil/', {
                        headers: { 'Authorization': `Bearer ${token}` }
                    });
                    setUser(response.data);
                } catch (error) {
                    console.error('Error cargando usuario:', error);
                }
            }
        };
        fetchUser();
    }, []);

    const handleLogout = () => {
        localStorage.removeItem('access_token');
        localStorage.removeItem('refresh_token');
        axios.defaults.headers.common['Authorization'] = null;
        setUser(null);
        navigate(AUTH_ROUTES.LOGIN);
    };

    const handleChangeUser = () => {
        localStorage.removeItem('access_token');
        localStorage.removeItem('refresh_token');
        axios.defaults.headers.common['Authorization'] = null;
        setUser(null);
        navigate(AUTH_ROUTES.LOGIN);
    };

    const isAdmin = user?.is_staff;
    
    const adminLinks = [
        { name: 'Dashboard', href: ADMIN_ROUTES.DASHBOARD },
        { name: 'Turnos', href: ADMIN_ROUTES.TURNOS },
        { name: 'Rutinas', href: ADMIN_ROUTES.GESTIONAR_RUTINAS },
        { name: 'Servicios', href: ADMIN_ROUTES.SERVICIOS },
        { name: 'Contenido Educativo', href: ADMIN_ROUTES.CONTENIDO_EDUCATIVO },
        { name: 'Agenda', href: ADMIN_ROUTES.AGENDA },
    ];

    const clientLinks = [
        { name: 'Mis Turnos', href: CLIENTE_ROUTES.MIS_TURNOS },
        { name: 'Reservar', href: CLIENTE_ROUTES.RESERVAR },
        { name: 'Rutinas', href: CLIENTE_ROUTES.CATALOGO_RUTINAS },
        { name: 'Servicios', href: CLIENTE_ROUTES.CATALOGO_SERVICIOS },
    ];

    const navLinks = isAdmin ? adminLinks : clientLinks;

    const isActive = (href) => location.pathname === href;

    return (
        <header className="sticky top-0 z-40 shadow-sm" style={{ backgroundColor: '#C1B4A4' }}>
            <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
                <div className="flex items-center justify-between h-16 gap-4">
                    {/* Logo */}
                    <div className="flex-shrink-0">
                        <Link to={isAdmin ? ADMIN_ROUTES.DASHBOARD : CLIENTE_ROUTES.PERFIL}>
                            <h1 className="text-xl sm:text-2xl font-bold text-gray-800 tracking-tight">Bohemia Hair</h1>
                        </Link>
                    </div>

                    {/* Mobile Menu Button */}
                    <button
                        className="md:hidden flex flex-col gap-1 focus:outline-none"
                        onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
                        aria-label="Menu"
                    >
                        <span className="w-6 h-0.5 bg-gray-800 rounded transition-all"></span>
                        <span className="w-6 h-0.5 bg-gray-800 rounded transition-all"></span>
                        <span className="w-6 h-0.5 bg-gray-800 rounded transition-all"></span>
                    </button>

                    {/* Navigation */}
                    <nav className={`${mobileMenuOpen ? 'block' : 'hidden'} md:flex absolute md:relative top-16 md:top-0 left-0 right-0 md:justify-center flex-col md:flex-row gap-0 md:gap-0 md:flex-1 w-full md:w-auto`} style={{ backgroundColor: 'rgba(193, 180, 164, 0.3)' }}>
                        {navLinks.map((link) => (
                            <Link
                                key={link.href}
                                to={link.href}
                                className={`px-4 md:px-3 py-3 md:py-2 font-medium text-sm transition-all ${
                                    isActive(link.href) 
                                        ? 'text-gray-800 border-b-2 md:border-b-2' 
                                        : 'text-gray-700 hover:text-gray-800'
                                }`}
                                style={{ 
                                    borderColor: isActive(link.href) ? '#817773' : 'transparent',
                                    backgroundColor: isActive(link.href) ? 'rgba(255, 255, 255, 0.3)' : 'transparent'
                                }}
                                onMouseEnter={(e) => !isActive(link.href) && (e.target.style.backgroundColor = 'rgba(193, 180, 164, 0.4)')}
                                onMouseLeave={(e) => !isActive(link.href) && (e.target.style.backgroundColor = 'transparent')}
                                onClick={() => setMobileMenuOpen(false)}
                            >
                                {link.name}
                            </Link>
                        ))}
                    </nav>

                    {/* User Section */}
                    <div className="flex-shrink-0 flex items-center gap-2">
                        {user ? (
                            <>
                                <div className="hidden lg:block">
                                    <CampanaNotificaciones />
                                </div>
                                <div className="relative">
                                    <button
                                        className="flex items-center gap-2 px-2 py-1 md:px-3 md:py-2 rounded-lg transition-all text-gray-800 font-medium text-sm"
                                        style={{ backgroundColor: 'rgba(255, 255, 255, 0.3)' }}
                                        onMouseEnter={(e) => e.target.style.backgroundColor = 'rgba(255, 255, 255, 0.5)'}
                                        onMouseLeave={(e) => e.target.style.backgroundColor = 'rgba(255, 255, 255, 0.3)'}
                                        onClick={() => setDropdownOpen(!dropdownOpen)}
                                    >
                                        <div className="w-7 h-7 md:w-8 md:h-8 rounded-full flex items-center justify-center text-xs md:text-sm font-bold text-white" style={{ backgroundColor: '#817773' }}>
                                            {user.first_name
                                                ? user.first_name[0].toUpperCase()
                                                : user.email[0].toUpperCase()}
                                        </div>
                                        <span className="hidden sm:inline max-w-xs overflow-hidden text-ellipsis whitespace-nowrap text-xs md:text-sm text-gray-800">
                                            {user.first_name || user.email}
                                        </span>
                                        <span className={`text-xs transition-transform text-gray-600 ${dropdownOpen ? 'rotate-180' : ''}`}>▼</span>
                                    </button>

                                    {dropdownOpen && (
                                        <div className="absolute top-full right-0 mt-2 w-56 bg-white rounded-lg shadow-lg border border-gray-200 z-50 animate-fade-in-up">
                                            <div className="px-4 py-3 border-b" style={{ backgroundColor: '#F5F0EB', borderColor: '#E8DCC4' }}>
                                                <p className="text-xs md:text-sm text-gray-600 break-all">{user.email}</p>
                                                <span className="inline-block mt-2 px-2 py-1 rounded text-xs font-semibold text-white" style={{ backgroundColor: '#C1B4A4' }}>
                                                    {user.is_staff ? 'Administrador' : 'Cliente'}
                                                </span>
                                            </div>
                                            {!isAdmin && (
                                                <>
                                                    <Link
                                                        to={CLIENTE_ROUTES.PERFIL}
                                                        className="block px-4 py-2 hover:bg-gray-50 text-sm text-gray-700 transition-colors"
                                                        onClick={() => setDropdownOpen(false)}
                                                    >
                                                        Mi Perfil
                                                    </Link>
                                                    <Link
                                                        to={CLIENTE_ROUTES.MI_AGENDA}
                                                        className="block px-4 py-2 hover:bg-gray-50 text-sm text-gray-700 transition-colors border-b border-gray-100"
                                                        onClick={() => setDropdownOpen(false)}
                                                    >
                                                        Mi Agenda
                                                    </Link>
                                                </>
                                            )}
                                            <button
                                                className="w-full text-left px-4 py-2 hover:bg-red-50 text-sm text-red-600 font-medium transition-colors"
                                                onClick={() => {
                                                    handleChangeUser();
                                                    setDropdownOpen(false);
                                                }}
                                            >
                                                Cambiar Usuario
                                            </button>
                                            <button
                                                className="w-full text-left px-4 py-2 hover:bg-red-50 text-sm text-red-600 font-medium transition-colors"
                                                onClick={() => {
                                                    handleLogout();
                                                    setDropdownOpen(false);
                                                }}
                                            >
                                                Cerrar Sesión
                                            </button>
                                        </div>
                                    )}
                                </div>
                            </>
                        ) : null}
                    </div>
                </div>
            </div>
        </header>
    );
};

export default Header;
