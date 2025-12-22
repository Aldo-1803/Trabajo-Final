// Rutas de autenticación
export const AUTH_ROUTES = {
  LOGIN: '/login',
  REGISTRO: '/registro',
  RECUPERAR_CONTRASENA: '/recuperar-contrasena',
};

// Rutas de cliente
export const CLIENTE_ROUTES = {
  PERFIL: '/perfil',
  EDITAR_PERFIL: '/editar-perfil',
  RESERVAR: '/reservar',
  MIS_TURNOS: '/mis-turnos',
  MI_AGENDA: '/mi-agenda',
  CATALOGO_RUTINAS: '/catalogo-rutinas',
  MIS_RUTINAS: '/mis-rutinas',
  RUTINA_DETALLE: '/rutina/:id',
  CATALOGO_SERVICIOS: '/catalogo-servicios',
  SERVICIO_DETALLE: '/servicio/:servicioId',
};

// Rutas de admin
export const ADMIN_ROUTES = {
  DASHBOARD: '/admin-dashboard',
  NUEVO_TURNO: '/admin/nuevo-turno',
  TURNOS: '/admin/turnos',
  GESTIONAR_RUTINAS: '/admin/gestionar-rutinas',
  RUTINA_DETALLE: '/admin/rutina/:id',
  SERVICIOS: '/admin/servicios',
  REGLAS: '/admin/reglas',
  PRODUCTOS: '/admin/productos',
  USUARIOS: '/admin/usuarios',
  CLIENTES: '/admin/clientes',
  EQUIPAMIENTO: '/admin/equipamiento',
  AGENDA: '/admin/agenda',
};

// Rutas sin Header
export const NO_HEADER_ROUTES = [
  AUTH_ROUTES.LOGIN,
  AUTH_ROUTES.REGISTRO,
  AUTH_ROUTES.RECUPERAR_CONTRASENA,
];
