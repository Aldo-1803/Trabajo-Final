import React, { useState, useEffect } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import axios from 'axios';
import CampanaNotificaciones from './CampanaNotificaciones';

const Header = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const [isAdmin, setIsAdmin] = useState(false);
  const [user, setUser] = useState(null);
  const [menuOpen, setMenuOpen] = useState(false);

  useEffect(() => {
    const token = localStorage.getItem('access_token');
    if (token) {
      fetchUserProfile();
    }
  }, []);

  const fetchUserProfile = async () => {
    try {
      const token = localStorage.getItem('access_token');
      const response = await axios.get('http://127.0.0.1:8000/api/usuarios/perfil/', {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      setUser(response.data);
      setIsAdmin(response.data.is_staff);
    } catch (error) {
      console.error('Error fetching profile:', error);
    }
  };

  const handleLogout = () => {
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
    navigate('/login');
  };

  const navItems = isAdmin
    ? [
        { label: 'Dashboard', path: '/admin-dashboard' },
        { label: 'Usuarios', path: '/admin/usuarios' },
        { label: 'Clientes', path: '/admin/clientes' },
        { label: 'Servicios', path: '/admin/servicios' },
        { label: 'Productos', path: '/admin/productos' },
        { label: 'Equipamiento', path: '/admin/equipamiento' },
      ]
    : [
        { label: 'Mi Perfil', path: '/perfil' },
        { label: 'Rutinas', path: '/catalogo-rutinas' },
        { label: 'Mis Rutinas', path: '/mis-rutinas' },
        { label: 'Mis Turnos', path: '/mis-turnos' },
      ];

  return (
    <header className="bg-white border-b sticky top-0 z-50" style={{ borderColor: '#D5D1CC' }}>
      <div className="w-full px-3 sm:px-4 md:px-6 lg:px-8">
        <div className="flex justify-between items-center h-14 sm:h-16">
          
          {/* Logo */}
          <div className="flex-shrink-0 min-w-fit">
            <button
              onClick={() => navigate(isAdmin ? '/admin-dashboard' : '/perfil')}
              className="text-lg sm:text-xl md:text-2xl font-bold transition whitespace-nowrap"
              style={{ color: '#817773' }}
            >
              Bohemia Hair
            </button>
          </div>

          {/* Desktop Navigation */}
          <nav className="hidden lg:flex gap-2 xl:gap-6 flex-1 justify-center">
            {navItems.map((item) => (
              <button
                key={item.path}
                onClick={() => navigate(item.path)}
                className={`text-xs xl:text-sm font-medium transition whitespace-nowrap px-2 py-2 rounded ${
                  location.pathname === item.path
                    ? 'border-b-2'
                    : 'hover:bg-opacity-50'
                }`}
                style={{
                  color: location.pathname === item.path ? '#817773' : '#8B8682',
                  borderColor: location.pathname === item.path ? '#AB9A91' : 'transparent',
                  backgroundColor: location.pathname === item.path ? '#F5EBE0' : 'transparent'
                }}
              >
                {item.label}
              </button>
            ))}
          </nav>

          {/* Right Section */}
          <div className="flex items-center gap-2 sm:gap-3 md:gap-4 flex-shrink-0">
            {/* Campana de Notificaciones */}
            <div className="text-gray-700 hover:text-pink-600 transition">
              <CampanaNotificaciones />
            </div>

            {/* Mobile Menu Button */}
            <button
              onClick={() => setMenuOpen(!menuOpen)}
              className="lg:hidden p-2 rounded-lg transition"
              style={{ color: '#817773', backgroundColor: '#F5EBE0' }}
              aria-label="Menu"
            >
              <svg className="w-5 h-5 sm:w-6 sm:h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
              </svg>
            </button>

            {/* User Info - Hidden on very small screens */}
            {user && (
              <div className="hidden sm:flex items-center gap-2 md:gap-3">
                <div className="flex flex-col items-end">
                  <p className="text-xs md:text-sm font-medium truncate max-w-[120px] md:max-w-none" style={{ color: '#5A5451' }}>
                    {user.nombre || user.email}
                  </p>
                  <p className="text-xs" style={{ color: '#8B8682' }}>{isAdmin ? 'Admin' : 'Cliente'}</p>
                </div>
                
                {/* Avatar */}
                <div className="w-8 sm:w-9 md:w-10 h-8 sm:h-9 md:h-10 rounded-full flex items-center justify-center text-white font-bold text-xs sm:text-sm flex-shrink-0" style={{ background: 'linear-gradient(135deg, #AB9A91 0%, #817773 100%)' }}>
                  {user.nombre?.charAt(0).toUpperCase() || user.email?.charAt(0).toUpperCase() || 'U'}
                </div>
              </div>
            )}

            {/* Logout Button */}
            <button
              onClick={handleLogout}
              className="px-3 sm:px-4 py-2 text-xs sm:text-sm font-medium text-white rounded-lg transition flex-shrink-0 whitespace-nowrap"
              style={{ backgroundColor: '#AB9A91' }}
              onMouseEnter={(e) => e.target.style.backgroundColor = '#817773'}
              onMouseLeave={(e) => e.target.style.backgroundColor = '#AB9A91'}
            >
              Salir
            </button>
          </div>
        </div>

        {/* Mobile Menu */}
        {menuOpen && (
          <nav className="lg:hidden border-t py-3 space-y-2 pb-3" style={{ borderColor: '#D5D1CC' }}>
            {navItems.map((item) => (
              <button
                key={item.path}
                onClick={() => {
                  navigate(item.path);
                  setMenuOpen(false);
                }}
                className="block w-full text-left px-3 py-2 rounded-lg transition text-sm"
                style={{
                  backgroundColor: location.pathname === item.path ? '#E3D5CA' : 'transparent',
                  color: location.pathname === item.path ? '#817773' : '#5A5451',
                  fontWeight: location.pathname === item.path ? 'bold' : 'normal'
                }}
              >
                {item.label}
              </button>
            ))}
          </nav>
        )}
      </div>
    </header>
  );
};

export default Header;
