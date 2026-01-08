import React, { useState, useEffect } from 'react';
import { Link, useNavigate, useLocation } from 'react-router-dom';
import axios from 'axios';
import { CLIENTE_ROUTES, ADMIN_ROUTES, AUTH_ROUTES } from '../routes/routes';
import '../styles/header.css';

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
        <header className="header-container">
            <div className="header-content">
                {/* Logo */}
                <div className="header-logo">
                    <Link to={isAdmin ? ADMIN_ROUTES.DASHBOARD : CLIENTE_ROUTES.PERFIL}>
                        <h1>Bohemia Hair</h1>
                    </Link>
                </div>

                {/* Mobile Menu Button */}
                <button
                    className="mobile-menu-btn"
                    onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
                    aria-label="Menu"
                >
                    <span></span>
                    <span></span>
                    <span></span>
                </button>

                {/* Navigation */}
                <nav className={`header-nav ${mobileMenuOpen ? 'active' : ''}`}>
                    {navLinks.map((link) => (
                        <Link
                            key={link.href}
                            to={link.href}
                            className={`nav-link ${isActive(link.href) ? 'active' : ''}`}
                            onClick={() => setMobileMenuOpen(false)}
                        >
                            {link.name}
                        </Link>
                    ))}
                </nav>

                {/* User Section */}
                <div className="header-user">
                    {user ? (
                        <div className="user-dropdown">
                            <button
                                className="user-button"
                                onClick={() => setDropdownOpen(!dropdownOpen)}
                            >
                                <div className="user-avatar">
                                    {user.first_name
                                        ? user.first_name[0].toUpperCase()
                                        : user.email[0].toUpperCase()}
                                </div>
                                <span className="user-name">{user.first_name || user.email}</span>
                                <span className={`chevron ${dropdownOpen ? 'open' : ''}`}>▼</span>
                            </button>

                            {dropdownOpen && (
                                <div className="dropdown-menu">
                                    <div className="dropdown-header">
                                        <p className="user-email">{user.email}</p>
                                        <span className="user-role">
                                            {user.is_staff ? 'Administrador' : 'Cliente'}
                                        </span>
                                    </div>
                                    <hr />
                                    {!isAdmin && (
                                        <>
                                            <Link
                                                to={CLIENTE_ROUTES.PERFIL}
                                                className="dropdown-item"
                                                onClick={() => setDropdownOpen(false)}
                                            >
                                                Mi Perfil
                                            </Link>
                                            <Link
                                                to={CLIENTE_ROUTES.MI_AGENDA}
                                                className="dropdown-item"
                                                onClick={() => setDropdownOpen(false)}
                                            >
                                                Mi Agenda
                                            </Link>
                                            <hr />
                                        </>
                                    )}
                                    <button
                                        className="dropdown-item danger"
                                        onClick={() => {
                                            handleChangeUser();
                                            setDropdownOpen(false);
                                        }}
                                    >
                                        Cambiar Usuario
                                    </button>
                                    <button
                                        className="dropdown-item danger"
                                        onClick={() => {
                                            handleLogout();
                                            setDropdownOpen(false);
                                        }}
                                    >
                                        Cerrar Sesion
                                    </button>
                                </div>
                            )}
                        </div>
                    ) : null}
                </div>
            </div>
        </header>
    );
};

export default Header;
