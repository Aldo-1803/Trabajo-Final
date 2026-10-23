import React, { useState, useEffect } from 'react';
import { Link, useNavigate, useLocation } from 'react-router-dom';
import axios from 'axios';
import { AUTH_ROUTES } from '../routes/routes';
import { useSession } from '../context/SessionContext';
import {
    getVisibleNavigationItems,
    NAVIGATION_PLACEMENT
} from '../navigation/navigationConfig';
import { getLandingPath } from '../utils/sessionLanding';
import CampanaNotificaciones from './CampanaNotificaciones';
import { IconCart } from './common/Icons';

const Header = () => {
    const [dropdownOpen, setDropdownOpen] = useState(false);
    const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
    const [empresaNombre, setEmpresaNombre] = useState('Bohemia Hair');
    const navigate = useNavigate();
    const location = useLocation();
    const {
        session,
        user,
        businessRole,
        loading,
        authenticated,
        error,
        clearSession,
        hasPermission,
        hasAnyPermission,
        hasProfile
    } = useSession();

    useEffect(() => {
        const fetchEmpresaNombre = async () => {
            try {
                const res = await axios.get('http://127.0.0.1:8000/api/gestion/configuracion/publica/');
                const nombre = res.data?.empresa_nombre?.trim();
                if (nombre) {
                    setEmpresaNombre(nombre);
                }
            } catch (error) {
                console.error('Error cargando nombre de empresa:', error);
            }
        };

        fetchEmpresaNombre();
    }, []);

    const leaveSession = () => {
        clearSession();
        navigate(AUTH_ROUTES.LOGIN);
    };

    const navigationAccess = {
        businessRole,
        loading,
        authenticated,
        error,
        hasPermission,
        hasAnyPermission,
        hasProfile
    };

    const primaryItems = getVisibleNavigationItems(
        navigationAccess,
        NAVIGATION_PLACEMENT.PRIMARY
    );
    const accountItems = getVisibleNavigationItems(
        navigationAccess,
        NAVIGATION_PLACEMENT.ACCOUNT
    );
    const actionItems = getVisibleNavigationItems(
        navigationAccess,
        NAVIGATION_PLACEMENT.ACTION
    );
    const cartItem = actionItems.find((item) => item.id === 'client-cart');
    const landingPath = getLandingPath(session) || AUTH_ROUTES.LOGIN;
    const roleLabel = businessRole || 'Sin rol de acceso';

    const isActive = (path) => location.pathname === path;

    return (
        <header className="sticky top-0 z-40 shadow-sm" style={{ backgroundColor: '#C1B4A4' }}>
            <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
                <div className="flex items-center justify-between h-16 gap-4">
                    {/* Logo */}
                    <div className="flex-shrink-0">
                        <Link to={landingPath} aria-label="Ir al inicio de la sesión">
                            <h1 className="text-xl sm:text-2xl font-bold text-gray-800 tracking-tight">{empresaNombre}</h1>
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
                        {primaryItems.map((item) => (
                            <Link
                                key={item.id}
                                to={item.path}
                                className={`px-4 md:px-3 py-3 md:py-2 font-medium text-sm transition-all ${
                                    isActive(item.path)
                                        ? 'text-gray-800 border-b-2 md:border-b-2' 
                                        : 'text-gray-700 hover:text-gray-800'
                                }`}
                                style={{ 
                                    borderColor: isActive(item.path) ? '#817773' : 'transparent',
                                    backgroundColor: isActive(item.path) ? 'rgba(255, 255, 255, 0.3)' : 'transparent'
                                }}
                                onMouseEnter={(e) => !isActive(item.path) && (e.target.style.backgroundColor = 'rgba(193, 180, 164, 0.4)')}
                                onMouseLeave={(e) => !isActive(item.path) && (e.target.style.backgroundColor = 'transparent')}
                                onClick={() => setMobileMenuOpen(false)}
                            >
                                {item.label}
                            </Link>
                        ))}
                    </nav>

                    {/* User Section */}
                    <div className="flex-shrink-0 flex items-center gap-2">
                        {authenticated && !loading && !error && user ? (
                            <>
                                <div className="hidden lg:block">
                                    <CampanaNotificaciones />
                                </div>
                                
                                {/* Carrito de Compras */}
                                {cartItem && (
                                    <Link
                                        to={cartItem.path}
                                        className="relative flex items-center justify-center w-10 h-10 rounded-lg transition-all"
                                        style={{ backgroundColor: 'rgba(255, 255, 255, 0.3)' }}
                                        onMouseEnter={(e) => e.currentTarget.style.backgroundColor = 'rgba(255, 255, 255, 0.5)'}
                                        onMouseLeave={(e) => e.currentTarget.style.backgroundColor = 'rgba(255, 255, 255, 0.3)'}
                                        title="Carrito de compras"
                                    >
                                        <IconCart className="h-5 w-5 text-gray-800" />
                                    </Link>
                                )}
                                
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
                                                     {roleLabel}
                                                 </span>
                                             </div>
                                             {accountItems.map((item) => (
                                                 <Link
                                                     key={item.id}
                                                     to={item.path}
                                                     className="block px-4 py-2 hover:bg-gray-50 text-sm text-gray-700 transition-colors"
                                                     onClick={() => setDropdownOpen(false)}
                                                 >
                                                     {item.label}
                                                 </Link>
                                             ))}
                                             <button
                                                 className="w-full text-left px-4 py-2 hover:bg-red-50 text-sm text-red-600 font-medium transition-colors"
                                                 onClick={() => {
                                                     leaveSession();
                                                     setDropdownOpen(false);
                                                }}
                                            >
                                                Cambiar Usuario
                                            </button>
                                            <button
                                                 className="w-full text-left px-4 py-2 hover:bg-red-50 text-sm text-red-600 font-medium transition-colors"
                                                 onClick={() => {
                                                     leaveSession();
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
